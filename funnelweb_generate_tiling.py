#ipython --pylab

# Test the various implementations of assign_fibre

import taipan.core as tp
import taipan.tiling as tl
from astropy.table import Table
import matplotlib.patches as mpatches
# from mpl_toolkits.basemap import Basemap
import random
import sys
import datetime


#Change defaults
tp.STANDARDS_PER_TILE_MIN = 3

try:
    if all_targets and guide_targets and standard_targets:
        pass
except NameError:
    print 'Importing test data...'
    tabdata = Table.read('/Users/mireland/tel/funnelweb/'
        '2mass_AAA_i7-10_offplane.csv')
    guidedata = Table.read('/Users/mireland/tel/funnelweb/'
        '2mass_AAA_i7-10_offplane.csv')
    guidedata = guidedata[guidedata['imag'] > 9.7] 
    standdata = Table.read('/Users/mireland/tel/funnelweb/'
        '2mass_AAA_i7-10_offplane.csv')
    standdata = standdata[standdata['imag'] > 9.9] 
    print 'Generating targets...'
    all_targets = [tp.TaipanTarget(str(r['mainid']), r['raj2000'], r['dej2000'], 
        priority=1, mag=r['imag'],difficulty=1) for r in tabdata 
        if 30 < r['raj2000'] < 43 and -34 < r['dej2000'] < -26]
    guide_targets = [tp.TaipanTarget(str(r['mainid']), r['raj2000'], r['dej2000'], 
        priority=1, mag=r['imag'], difficulty=1, guide=True) for r in guidedata 
        if 30 < r['raj2000'] < 43 and -34 < r['dej2000'] < -26]
    standard_targets = [tp.TaipanTarget(str(r['mainid']), r['raj2000'], r['dej2000'], 
        priority=1, mag=r['imag'], difficulty=1, standard=True) for r in standdata 
        if 30 < r['raj2000'] < 43 and -34 < r['dej2000'] < -26]

# tp.compute_target_difficulties(all_targets, ncpu=4)
# sys.exit()

# sys.exit()

# Ensure the objects are re type-cast as new instances of TaipanTarget
for t in all_targets:
    t.__class__ = tp.TaipanTarget
for t in guide_targets:
    t.__class__ = tp.TaipanTarget
for t in standard_targets:
    t.__class__ = tp.TaipanTarget


# Make a copy of all_targets list for use in assigning fibres
candidate_targets = all_targets[:]
random.shuffle(candidate_targets)

tiling_method = 'SH'
tiling_set_size = 100
alloc_method = 'combined_weighted'
ranking_method = 'combined-weighted-sum'
combined_weight = 1.0
sequential_ordering = (1,2)
completeness_target = 0.999 #0.975

print 'Commencing tiling...'
start = datetime.datetime.now()
test_tiling, tiling_completeness, remaining_targets = tl.generate_tiling_funnelweb(
    candidate_targets, standard_targets, guide_targets,
    mag_ranges_prioritise = [[7,8],[8,9]],
    prioritise_extra = 4,
    completeness_priority = 4,
    mag_ranges = [[7,9],[8,10]],
    completeness_target=completeness_target,
    ranking_method=ranking_method,
    tiling_method=tiling_method, randomise_pa=True, 
    tiling_set_size=tiling_set_size,
    ra_min=30., ra_max=43., dec_min=-34., dec_max=-26.,
    randomise_SH=True, tiling_file='ipack.3.4112.txt',
    tile_unpick_method=alloc_method, sequential_ordering=sequential_ordering,
    combined_weight=combined_weight,
    rank_supplements=False, repick_after_complete=True,
    recompute_difficulty=True, disqualify_below_min=True)
end = datetime.datetime.now()

# Analysis
time_to_complete = (end - start).total_seconds()
targets_per_tile = [t.count_assigned_targets_science() for t in test_tiling]
standards_per_tile = [t.count_assigned_targets_standard() for t in test_tiling]
guides_per_tile = [t.count_assigned_targets_guide() for t in test_tiling]

print 'TILING STATS'
print '------------'
print 'Greedy tiling complete in %d:%2.1f' % (int(floor(time_to_complete/60.)),
    time_to_complete % 60.)
print '%d targets required %d tiles' % (len(all_targets), len(test_tiling), )
print 'Average %3.1f targets per tile' % np.average(targets_per_tile)
print '(min %d, max %d, median %d, std %2.1f' % (min(targets_per_tile),
    max(targets_per_tile), np.median(targets_per_tile), 
    np.std(targets_per_tile))

# Plot these results (requires ipython --pylab)

clf()
fig = gcf()
fig.set_size_inches(12., 18.)

# Tile positions
ax1 = fig.add_subplot(421, projection='aitoff')
ax1.grid(True)
# for tile in test_tiling:
    # tile_verts = np.asarray([tp.compute_offset_posn(tile.ra, 
    #     tile.dec, tp.TILE_RADIUS, float(p)) for p in range(361)])
    # tile_verts = np.asarray([tp.aitoff_plottable(xy, ra_offset=180.) for xy
    #     in tile_verts])
    # ec = 'k'
    # tile_circ = mpatches.Polygon(tile_verts, closed=False,
    #     edgecolor=ec, facecolor='none', lw=.5)
    # ax1.add_patch(tile_circ)
ax1.plot([np.radians(t.ra - 180.) for t in test_tiling], [np.radians(t.dec) 
    for t in test_tiling],
    'ko', lw=0, ms=1)
ax1.set_title('Tile centre positions')

show()
draw()

# Box-and-whisker plots of number distributions
ax0 = fig.add_subplot(423)
ax0.boxplot([targets_per_tile, standards_per_tile, guides_per_tile],
    vert=False)
ax0.set_yticklabels(['T', 'S', 'G'])
ax0.set_title('Box-and-whisker plots of number of assignments')

show()
draw()

# Move towards completeness
ax3 = fig.add_subplot(223)
targets_per_tile_sorted = sorted(targets_per_tile, key=lambda x: -1.*x)
xpts = np.asarray(range(len(targets_per_tile_sorted))) + 1
ypts = [np.sum(targets_per_tile_sorted[:i+1]) for i in xpts]
ax3.plot(xpts, ypts, 'k-', lw=.9)
ax3.plot(len(test_tiling), np.sum(targets_per_tile), 'ro',
    label='No. of tiles: %d' % len(test_tiling))
ax3.hlines(len(all_targets), ax3.get_xlim()[0], ax3.get_xlim()[1], lw=.75,
    colors='k', linestyles='dashed', label='100% completion')
ax3.hlines(0.975 * len(all_targets), ax3.get_xlim()[0], ax3.get_xlim()[1], 
    lw=.75,
    colors='k', linestyles='dashdot', label='97.5% completion')
ax3.hlines(0.95 * len(all_targets), ax3.get_xlim()[0], ax3.get_xlim()[1], lw=.75,
    colors='k', linestyles='dotted', label='95% completion')
ax3.legend(loc='lower right', title='Time to %3.1f comp.: %dm:%2.1fs' % (
    completeness_target * 100., 
    int(floor(time_to_complete/60.)), time_to_complete % 60.))
ax3.set_title('Completeness progression')
ax3.set_xlabel('No. of tiles')
ax3.set_ylabel('No. of assigned targets')

show()
draw()

# No. of targets per tile
target_range = max(targets_per_tile) - min(targets_per_tile)
ax2 = fig.add_subplot(322)
ax2.hist(targets_per_tile, bins=target_range, align='right')
ax2.vlines(120, ax2.get_ylim()[0], ax2.get_ylim()[1], linestyles='dashed',
    colors='k', label='Ideally-filled tile')
ax2.legend(loc='upper right')
ax2.set_xlabel('No. of targets per tile')
ax2.set_ylabel('Frequency')

show()
draw()

# No. of standards per tile
standard_range = max(standards_per_tile) - min(standards_per_tile)
ax4 = fig.add_subplot(324)
ax4.hist(standards_per_tile, bins=standard_range, align='right')
ax4.vlines(tp.STANDARDS_PER_TILE, ax4.get_ylim()[0], ax4.get_ylim()[1], 
    linestyles='dashed',
    colors='k', label='Ideally-filled tile')
ax4.vlines(tp.STANDARDS_PER_TILE_MIN, ax4.get_ylim()[0], ax4.get_ylim()[1], 
    linestyles='dotted',
    colors='k', label='Minimum standards per tile')
ax4.set_xlabel('No. of standards per tile')
ax4.set_ylabel('Frequency')
ax4.legend(loc='upper left')

show()
draw()

# No. of guides per tile
guide_range = max(guides_per_tile) - min(guides_per_tile)
ax5 = fig.add_subplot(326)
ax5.hist(guides_per_tile, bins=guide_range, align='right')
ax5.vlines(tp.GUIDES_PER_TILE, ax5.get_ylim()[0], ax5.get_ylim()[1], 
    linestyles='dashed',
    colors='k', label='Ideally-filled tile')
ax5.vlines(tp.GUIDES_PER_TILE_MIN, ax5.get_ylim()[0], ax5.get_ylim()[1], 
    linestyles='dotted',
    colors='k', label='Minimum guides per tile')
ax5.set_xlabel('No. of guides per tile')
ax5.set_ylabel('Frequency')
ax5.legend(loc='upper left')

show()
draw()

supp_str = ''
if alloc_method == 'combined_weighted':
    supp_str = str(combined_weight)
elif alloc_method == 'sequential':
    supp_str = str(sequential_ordering)
ax2.set_title('GREEDY %s - %d targets, %s tiling, %s unpicking (%s)' % (
    ranking_method,len(all_targets),
    tiling_method, alloc_method, supp_str))
try:
    matplotlib.pyplot.tight_layout()
except:
    pass

show()
draw()

fig.savefig('test_tiling_greedy-%s_%s_%s%s.pdf' % (ranking_method,
    tiling_method, alloc_method, supp_str),
    fmt='pdf')
