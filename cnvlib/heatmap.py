"""The 'heatmap' command."""
import collections
import logging

import numpy as np
import pandas as pd
from sys import stderr
from matplotlib import pyplot as plt
from matplotlib.colors import ListedColormap

from skgenome.rangelabel import unpack_range
from . import plots


def OLD_cna2df(cna, do_desaturate):
    """Extract a dataframe of plotting points from a CopyNumArray."""
    points = cna.data.loc[:, ['start', 'end']]
    points['color'] = cna.log2.apply(plots.cvg2rgb, args=(do_desaturate,))
    points['log2'] = cna.log2
    return points
cna2df = lambda cna: cna.data.loc[:, ['start', 'end', 'log2']]


def do_heatmap(cnarrs, show_range=None, do_desaturate=False, by_bin=False, 
               delim_sampl=False, vertical=False, ax=None):
    """Plot copy number for multiple samples as a heatmap."""
    simplify = True
    if simplify:
        alt_genes = 'no'  # 'both' -> Show 'normal' + 'alt' genes ; 'alt'
        possible_alt_flags = ('no', 'both', 'alt')
        assert alt_genes in possible_alt_flags, f"{alt_genes=} instead being one of: {possible_alt_flags}"

        wanted_genes1 = "NRAS|MET|KRAS|ERBB2|EGFR|CTNNB1|PIK3CA|BRAF"
        #wanted_genes1 = "MSH2|EPCAM|ERBB2|PIK3CA"  # ONCOGENET genes
        wanted_genes2 = "FGFR2|FGFR3|PDGFRA|KIT|ALK|HRAS|PTEN|CDKN2A|TP53"
        #wanted_genes2 = "BRCA1|BRCA2"  # ONCOGENET genes
        if alt_genes == 'alt':
            wanted_genes = wanted_genes2
        elif alt_genes == 'both':
            wanted_genes = wanted_genes1 + '|' + wanted_genes2
        else:
            wanted_genes = wanted_genes1  # Default = 'classic' genes only
        print("[WARN_FELIX heatmap:do_heatmap()]: Keppin only wanted genes HERE\n"
              "(padding between each chrom is also further set to '0')\n"
              f"{wanted_genes=}", file=stderr)
        list_wanted = wanted_genes.split('|')
        keepin_wanted = lambda x: x.gene.split('|')[0] in list_wanted
        cnarrs = [a_cnarr.filter(keepin_wanted) for a_cnarr in cnarrs]

    if ax is None:
        _fig, axis = plt.subplots(figsize=(19,9))
    else:
        axis = ax

    # List sample names on the appropriate axis.
    if not vertical:
        axis.set_yticks([i + 0.5 for i in range(len(cnarrs))])
        axis.set_yticklabels([c.sample_id for c in cnarrs])
        axis.set_ylim(0, len(cnarrs))
        axis.set_ylabel('Samples')
    else:
        axis.set_xticks([i + 0.5 for i in range(len(cnarrs))])
        axis.set_xticklabels([c.sample_id for c in cnarrs], rotation=90)
        axis.set_xlim(0, len(cnarrs))
        axis.set_xlabel('Samples')

    if hasattr(axis, 'set_facecolor'):
        # matplotlib >= 2.0
        axis.set_facecolor('#DDDDDD')
    else:
        # Older matplotlib.
        axis.set_axis_bgcolor('#DDDDDD')

    if by_bin and show_range:
        try:
            a_cnarr = next(c for c in cnarrs if 'probes' not in c)
        except StopIteration:
            r_chrom, r_start, r_end = unpack_range(show_range)
            if r_start is not None or r_end is not None:
                raise ValueError(
                    'Need at least 1 .cnr input file if --by-bin (by_bin) and --chromosome (show_range) are both used '
                    'to specify a sub-chromosomal region.'
                )
        else:
            logging.info('Using sample {} to map {} to bin coordinates'.format(a_cnarr.sample_id, show_range))
            r_chrom, r_start, r_end = plots.translate_region_to_bins(show_range, a_cnarr)
    else:
        r_chrom, r_start, r_end = unpack_range(show_range)
    if r_start is not None or r_end is not None:
        logging.info('Showing log2 ratios in range {}:{}-{}'.format(r_chrom, r_start or 0, r_end or '*'))
    elif r_chrom:
        logging.info('Showing log2 ratios on chromosome {}'.format(r_chrom))

    # Group each file's probes/segments by chromosome
    sample_data = [collections.defaultdict(list) for _c in cnarrs]
    # Calculate the size (max endpoint value) of each chromosome
    chrom_sizes = collections.OrderedDict()
    for i, cnarr in enumerate(cnarrs):
        if by_bin:
            cnarr = plots.update_binwise_positions_simple(cnarr)

        if r_chrom:
            subcna = cnarr.in_range(r_chrom, r_start, r_end, mode='trim')
            sample_data[i][r_chrom] = cna2df(subcna)
            chrom_sizes[r_chrom] = max(subcna.end.iat[-1] if subcna else 0,
                                       chrom_sizes.get(r_chrom, 0))
        else:
            for chrom, subcna in cnarr.by_chromosome():
                sample_data[i][chrom] = cna2df(subcna)
                chrom_sizes[chrom] = max(subcna.end.iat[-1] if subcna else 0,
                                         chrom_sizes.get(r_chrom, 0))

    dict_log2 = collections.OrderedDict()
    if show_range:
        # Lay out only the selected chromosome
        # Set x-axis the chromosomal positions (in Mb), title as the selection
        if by_bin:
            MB = 1
            axis.set_xlabel('Position (bin)')
        else:
            MB = plots.MB
            axis.set_xlabel('Position (Mb)')

        axis.set_title(show_range)
        axis.tick_params(which='both', direction='out')
        axis.get_xaxis().tick_bottom()
        axis.get_yaxis().tick_left()
        if not vertical:
            axis.set_xlim((r_start or 0) * MB, (r_end or chrom_sizes[r_chrom]) * MB)
        else:
            axis.set_ylim((r_start or 0) * MB, (r_end or chrom_sizes[r_chrom]) * MB)

        # Plot the individual probe/segment coverages
        for i, sample in enumerate(sample_data):
            sampl_crow = sample[r_chrom]
            if not len(sampl_crow):
                logging.warning('Sample #{} has no data points in selection {}', i+1, show_range)
            sampl_crow['start'] *= MB
            sampl_crow['end'] *= MB
            dict_log2[i] = sampl_crow.set_index(['start', 'end']).log2

    else:
        # Lay out chromosome dividers and x-axis labels
        # (Just enough padding to avoid overlap with the divider line)
        # FELIX_MODIF (set 'pad=0' instead of 'pad=1'):
        chrom_offsets = plots.plot_chromosome_dividers(axis, chrom_sizes, 0, along='y' if vertical else 'x')
        # Plot the individual probe/segment coverages
        for i, sample in enumerate(sample_data):
            all_crows = []
            for chrom, curr_offset in chrom_offsets.items():
                crow = sample[chrom]
                if len(crow):
                    crow['start'] += curr_offset
                    crow['end'] += curr_offset
                    all_crows.append(crow)
                else:
                    logging.warning('Sample #%d has no datapoints', i+1)
            sampl_crow = pd.concat(all_crows, axis='index')
            dict_log2[i] = sampl_crow.set_index(['start', 'end']).log2

    log2_df = pd.DataFrame.from_dict(dict_log2)
    # Need to explicitly insert NaN-filled rows in-between 2 discontiguous intervals
    log2_df.reset_index(inplace=True)
    compt = 0
    for i in range(1, len(log2_df.index)):
        end_previous = log2_df.iloc[i-1].end
        start_current = log2_df.iloc[i].start
        if end_previous != start_current:  # Discontiguous.
            compt += 1
            log2_df.loc[i-1+0.5, :] = [end_previous, start_current] + [np.nan] * len(cnarrs)
    log2_df.sort_index(inplace=True)
    logging.debug('Inserted {} empty intervals (log2 = NaN for all samples).'.format(compt))

    # If no data for all samples, return an empty plot. Without this, further log2_df.end.iat[-1] causes an IndexError.
    if not len(log2_df):
        return axis

    # If shading='flat' (which is default) the dimensions of X and Y should be one greater than those of C.
    start2plt = np.array(log2_df.start.to_list() + [log2_df.end.iat[-1]])
    sampl2plt = np.array(range(len(cnarrs) + 1))
    if not vertical:
        dat2plot = log2_df.drop(['start', 'end'], axis='columns').transpose()
        x_pcolor, y_pcolor = start2plt, sampl2plt
    else:
        dat2plot = log2_df.drop(['start', 'end'], axis='columns')
        x_pcolor, y_pcolor = sampl2plt, start2plt

    cmap = ListedColormap([plots.cvg2rgb(x, do_desaturate) for x in np.linspace(-1.33, 1.33, 200)])
    im = axis.pcolormesh(x_pcolor, y_pcolor, dat2plot, vmin=-1.33, vmax=1.33, cmap=cmap)
    cbar = plt.colorbar(im, ax=axis, fraction=0.04, pad=0.03, shrink=0.6)
    cbar.set_label('log2', labelpad=0)
    
    if delim_sampl:
        delim_method = axis.axvline if vertical else axis.axhline
        for i in range(len(cnarrs)):
            delim_method(i, color='k')
    
    axis.invert_yaxis()

    # Add corresponding probe_name below x-axis:
    import matplotlib.transforms as transforms
    # 'blended' means smthg fixed no matter data limits:
    trans = transforms.blended_transform_factory(axis.transData, axis.transAxes)

    for j, a_cnarr in enumerate(cnarrs):
        if by_bin:
            a_cnarr = plots.update_binwise_positions_simple(a_cnarr)

        for _, a_probe in a_cnarr.data.iterrows():
            x_coord = a_probe.start + chrom_offsets[a_probe.chromosome]
            if abs(a_probe.log2) >= 0.49:
                axis.text(x_coord, j + 0.75, str(round(a_probe.log2, 2)),
                          color='gold', rotation=30)

            if j != 0: continue  # Need to do it once
            # Else, add probe_names below x-axis:
            axis.text(x_coord + 0.3, -0.04, plots.simplify_annot(a_probe.gene),
                      rotation=-45, transform=trans, rotation_mode='anchor')
    return axis
