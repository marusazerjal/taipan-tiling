# Simulate a full tiling of the Taipan galaxy survey

import sys
import logging
import taipan.core as tp
import taipan.tiling as tl
import taipan.scheduling as ts
import simulate as tsim

import pickle

import numpy as np
import atpy
import ephem
import random
import os

from src.resources.v0_0_1.readout.readCentroids import execute as rCexec
from src.resources.v0_0_1.readout.readGuides import execute as rGexec
from src.resources.v0_0_1.readout.readStandards import execute as rSexec
from src.resources.v0_0_1.readout.readScience import execute as rScexec
from src.resources.v0_0_1.readout.readTileScores import execute as rTSexec

from src.resources.v0_0_1.insert.insertTiles import execute as iTexec

import src.resources.v0_0_1.manipulate.makeTargetsRemain as mTR

from src.scripts.connection import get_connection

SIMULATE_LOG_PREFIX = 'SIMULATOR: '


def sim_prepare_db(cursor):
    """
    This initial step prepares the database for the simulation run by getting
    the fields in from the database, performing the initial tiling of fields,
    and then returning that information to the database for later use.

    Parameters
    ----------
    cursor

    Returns
    -------

    """

    # Ge the field centres in from the database
    logging.info(SIMULATE_LOG_PREFIX+'Loading targets')
    field_tiles = rCexec(cursor)
    candidate_targets = rScexec(cursor)
    guide_targets = rGexec(cursor)
    standard_targets = rSexec(cursor)

    logging.info(SIMULATE_LOG_PREFIX+'Generating first pass of tiles')
    # TEST ONLY: Trim the tile list to 10 to test DB write-out
    # field_tiles = random.sample(field_tiles, 40)
    candidate_tiles = tl.generate_tiling_greedy_npasses(candidate_targets,
                                                        standard_targets,
                                                        guide_targets,
                                                        1,
                                                        tiles=field_tiles,
                                                        )
    logging.info('First tile pass complete!')

    # 'Pickle' the tiles so they don't need to be regenerated later for tests
    with open('tiles.pobj', 'w') as tfile:
        pickle.dump(candidate_tiles, tfile)

    # Write the tiles to DB
    iTexec(cursor, candidate_tiles)

    # Compute the n_sci_rem and n_sci_obs for these tiles
    mTR.execute(cursor)

    return


def sim_do_night(cursor, date, date_start, date_end,
                 almanac_dict=None, dark_almanac=None,
                 save_new_almanacs=True):
    """
    Do a simulated 'night' of observations. This involves:
    - Determine the tiles to do tonight
    - 'Observe' them
    - Update the DB appropriately

    Parameters
    ----------
    cursor:
        The psycopg2 cursor for interacting with the database
    date:
        Python datetime.date object. This should be the local date that the
        night *starts* on, eg. the night of 23-24 July should be passed as
        23 July.
    date_start, date_end:
        The dates the observing run starts and ends on. These are required
        in order to compute the amount of time a certain field will remain
        observable.
    almanac_dict:
        Dictionary of taipan.scheduling.Almanac objects used for computing
        scheduling. Should be a dictionary with field IDs as keys, and values
        being either a single Almanac object, or a list of Almanac objects,
        covering the date in question. sim_do_night will calculate new/updated
        almanacs from date_start to date_end if almanacs are not passed for a
        particular field and/or date range. Defaults to None, at which point
        almanacs will be constructed for all fields over the specified date
        range.
    dark_almanac:
        As for almanac_list, but holds the dark almanacs, which simply
        specify dark or grey time on a per-datetime basis. Optional,
        defaults to None (so the necessary DarkAlmanac will be created).
    save_new_almanacs:
        Boolean value, denoting whether to save any new almanacs that are
        created by sim_do_night. Defaults to True.

    Returns
    -------
    Nil. All actions are internal or apply to the database.

    """
    # Do some input checking
    # Date needs to be in the range of date_start and date_end
    if date < date_start or date > date_end:
        raise ValueError('date must be in the range [date_start, date_end]')

    # Seed an alamnac dictionary if not passed
    if almanac_dict is None:
        almanac_dict = {}

    # Nest all the almanac_dict values inside a list for consistency.
    for k, v in almanac_dict.iteritems():
        if not isinstance(v, list):
            almanac_dict[k] = [v]
            # Check that all elements of input list are instances of Almanac
            if not np.all([isinstance(a, ts.Almanac) for a in v]):
                raise ValueError('The values of almanac_dict must contain '
                                 'single Almanacs of lists of Almanacs')

    if dark_almanac is not None:
        if not isinstance(dark_almanac, ts.DarkAlmanac):
            raise ValueError('dark_almanac must be None, or an instance of '
                             'DarkAlmanac')

    # Needs to do the following:
    # Read in the tiles that are awaiting observation, along with their scores
    scores_array = rTSexec(cursor, metrics=['cw_sum'])

    # Make sure we have an almanac for every field in the scores_array for the
    # correct date
    # If we don't, we'll need to make one
    # Note that, because of the way Python's scoping is set up, this will
    # permanently add the almanac to the input dictionary
    almanacs_existing = almanac_dict.keys()
    for row in scores_array:
        if row['field_id'] not in almanacs_existing:
            almanac_dict[row['field_id']] = [ts.Almanac(row['ra'], row['dec'],
                                                        date_start, date_end), ]
            if save_new_almanacs:
                almanac_dict[row['field_id']][0].save()
            almanacs_existing.append(row['field_id'])
        # Now, make sure that the almanacs actually cover the correct date range
        # If not, replace any existing almanacs with one super Almanac for the
        # entire range requested
        almanacs_relevant = {k: v for k, v in almanac_dict.iteritems()}
        for k in almanacs_relevant.iterkeys():
            try:
                almanacs_relevant[k] = [a for a in almanacs_relevant[k] if
                                        a.start_date <= date <= a.end_date][0]
            except KeyError:
                # This catches when no almanacs satisfy the condition in the
                # list constructor above
                almanac_dict[row['field_id']] = [
                    ts.Almanac(row['ra'], row['dec'],
                               date_start, date_end), ]
                if save_new_almanacs:
                    almanac_dict[row['field_id']][0].save()
                almanacs_relevant[
                    row['field_id']] = almanac_dict[row['field_id']]

    # Check that the dark almanac spans the relevant dates; if not,
    # regenerate it
    if dark_almanac is None or (dark_almanac.start_date > date or
                                dark_almanac.end_date < date):
        dark_almanac = ts.DarkAlmanac(date_start, end_date=date_end)

    # Compute sunrise and sunset for the night
    sunset, sunrise = ts.get_ephem_set_rise(date)

    # Compute how many observable hours are remaining in each of the fields

    # 'Observe' these tiles by updating the relevant database fields
    # Re-tile any affected areas and write new tiles back to DB



def execute(cursor, date_start, date_end, output_loc='.'):
    """
    Execute the simulation
    Parameters
    ----------
    cursor:
        psycopg2 cursor for communicating with the database.
    output_loc:
        String providing the path for placing the output plotting images.
        Defaults to '.' (ie. the present working directory). Directory must
        already exist.

    Returns
    -------
    Nil. Tiling outputs are written to the database (to simulate the action of
    the virtual observer), and plots are generated and placed in the output
    folder.
    """

    # This is just a rough scaffold to show the steps the code will need to
    # take

    # construct_league_table()
    # read_league_table()
    #
    # generate_initial_tiles()
    # write_tiles_to_db() # This creates the league table
    #
    # # DO EITHER:
    # date_curr = date_start
    # while date_curr < date_end:
    #     observe_night() # This will select & 'observe' tiles,
    #     # return the tiles observed
    #     manipulate_targets() # Update flags on successfully observe targets
    #     retile_fields () # Retile the affected fields
    #     curr_date += 1 # day
    #
    # # OR DO THIS INSTEAD:
    # observe_timeframe(date_start, date_end)
    # # This function will handle all of the above, but re-tile after each
    # # observation (and do all necessary DB interaction). This will be faster,
    # # as all the target handling can be done internally without
    # # reading/writing DB, *but* the function that do that then won't be
    # # prototyped
    #
    # read_in_observed_tiles()
    # generate_outputs()

    # TODO: Add check to skip this step if tables already exist
    # Currently dummied out with an is False
    if False:
        sim_prepare_db(cursor)

    fields = rCexec(cursor)
    # Construct the almanacs required
    logging.info('Constructing dark almanac...')
    dark_almanac = ts.DarkAlmanac(date_start, end_date=date_end,
                                  resolution=15.)
    dark_almanac.save()
    logging.info('Constructing field almanacs...')
    almanacs = {field.field_id: ts.Almanac(field.ra, field.dec, date_start,
                                           end_date=date_end, resolution=15.,
                                           minimum_airmass=2)
                for field in fields}
    # Work out which of the field almanacs already exist on disk
    files_on_disk = os.listdir()
    almanacs_existing = {k: v.generate_file_name() in files_on_disk
                         for (k, v) in almanacs.iteritems()}
    logging.info('Saving almanacs to disc...')
    for k in [k for (k, v) in almanacs_existing.iteritems() if v]:
        almanacs[k].save()

    return


if __name__ == '__main__':
    # Set the logging to write to terminal
    logging.info('Executing fullsurvey.py as file')
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Get a cursor
    # TODO: Correct package imports & references
    logging.debug('Getting connection')
    conn = get_connection()
    cursor = conn.cursor()
    # Execute the simulation based on command-line arguments
    logging.debug('Doing scripts execute function')
    execute(cursor, None, None)