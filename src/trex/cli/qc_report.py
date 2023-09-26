"""
Print a quality report from the run10x analysis.
"""
import logging
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

from . import setup_logging, CommandLineError, add_file_logging
from .. import __version__
from ..quality_control import (load_reads,
                               load_molecules,
                               load_molecules_corrected,
                               load_cells,
                               load_clone_ids,
                               load_umi_count_matrix,
                               get_read_per_molecule,
                               get_length_read,
                               get_clone_sizes, 
                               get_molecules_per_clone_ids,
                               get_clone_ids_per_clone,
                               get_clone_ids_per_cell,
                               get_unique_clone_ids_per_cell,
                               plot_discrete_histogram, 
                               add_clone_ids_per_clone,
                               hamming_distance_histogram,
                               jaccard_similarity_matrix,
                               jaccard_histogram,
                               plot_jaccard_matrix,
                               )


logger = logging.getLogger(__name__)


def add_arguments(parser):
    parser.add_argument(
        "path",
        type=Path,
        nargs="+",
        metavar="DIRECTORY",
        help="Path to a directory generated by 'trex run_10x'",
    )
    parser.add_argument(
        "--plot-jaccard-matrix",
        default=False,
        action="store_true"
    )
    parser.add_argument(
        "--plot-hamming-distance",
        default=False,
        action="store_true"
    )
    parser.add_argument(
        "--debug",
        default=False,
        action="store_true",
        help="Print some extra debugging messages",
    )


def make_clone_size_histogram(clones: pd.DataFrame) -> plt.Figure:
    """Plots the clone size histogram."""
    vals = get_clone_sizes(clones)
    mean = np.mean(vals)
    quantiles = np.quantile(vals, [0.25, 0.5, 0.75])

    this_txt = f'There are {len(vals)} clones. On average, they have {mean:.2f}\n' \
               f'cells, with a median of {quantiles[1]} and interquartile range of \n' \
               f'{quantiles[0]} - {quantiles[2]}. {sum(vals == 1)} clones have a single cell.'

    fig, ax = plt.subplots(1, 1)
    plot_discrete_histogram(vals, xlabel='Number of cells',
                            title='Number of cells per clone',
                            txt=this_txt, ax =ax)
    plt.subplots_adjust(bottom=0.3)
    return fig


def make_unique_clone_ids_per_clone(clones: pd.DataFrame,
                                    cells_filtered: pd.DataFrame) -> plt.Figure:
    """Plots the number of unique CloneIDs per clone histogram."""
    vals = get_clone_ids_per_clone(
        add_clone_ids_per_clone(clones, cells_filtered))
    mean = np.mean(vals)
    quantiles = np.quantile(vals, [0.25, 0.5, 0.75])

    this_txt = f'There are {len(vals)} clones. On average, they have {mean:.2f}\n' \
               f'unique CloneIDs, with a median of {quantiles[1]} and interquartile range of \n' \
               f'{quantiles[0]} - {quantiles[2]}. {sum(vals == 1)} clones have a single unique CloneID.'

    fig, ax = plt.subplots(1, 1)
    plot_discrete_histogram(vals, xlabel='Number of unique CloneIDs',
                            title='Number of unique CloneIDs per clone',
                            txt=this_txt, ax=ax)
    plt.subplots_adjust(bottom=0.3)
    return fig


def make_reads_per_molecule(reads: pd.DataFrame) -> plt.Figure:
    """Plots the histogram of reads per molecule."""
    vals = get_read_per_molecule(reads)
    mean = np.mean(vals)
    quantiles = np.quantile(vals, [0.25, 0.5, 0.75])

    this_txt = f'There are {len(vals)} viral CloneID molecules. On average, \n' \
               f'they have {mean:.2f} reads, with a median of {quantiles[1]} and \n' \
               f'interquartile range of {quantiles[0]} - {quantiles[2]}. {sum(vals == 1)} molecules have \n' \
               f'only a single read.'

    fig, ax = plt.subplots(1, 1)
    plot_discrete_histogram(vals, xlabel='Number of reads',
                            title='Number of reads per molecule',
                            txt=this_txt,
                            ax=ax)
    plt.subplots_adjust(bottom=0.3)
    return fig


def make_unique_clone_ids_per_cell(cells_filtered: pd.DataFrame) -> plt.Figure:
    """Plots the histogram of unique CloneIDs per cell at the end."""
    vals = get_unique_clone_ids_per_cell(cells_filtered,
                                        molecules_dataframe=False)
    mean = np.mean(vals)
    quantiles = np.quantile(vals, [0.25, 0.5, 0.75])

    this_txt = f'There are {len(vals)} cells in the end. On average, they have {mean:.2f}\n' \
               f'unique CloneIDs, with a median of {quantiles[1]} and interquartile range of \n' \
               f'{quantiles[0]} - {quantiles[2]}. {sum(vals == 1)} cells have only a single unique CloneID.'

    fig, ax = plt.subplots(1, 1)
    plot_discrete_histogram(vals, xlabel='Number of unique CloneIDs',
                            title='Number of unique CloneIDs per cell',
                            txt=this_txt, ax=ax)
    plt.subplots_adjust(bottom=0.3)
    return fig


def make_jaccard_similarity_plots(data_dir: Path) -> plt.Figure:
    """Calculates and plots the jaccard similarity histogram and matrix.
    Consider that it is not optimized so it might take a long time."""
    umi_count = load_umi_count_matrix(data_dir)
    jaccard_matrix = jaccard_similarity_matrix(umi_count)

    fig, axs = plt.subplots(2, 1, figsize=(11, 12),
                            gridspec_kw={'height_ratios': (1, 5)})
    jaccard_histogram(jaccard_matrix, ax=axs[0])
    plot_jaccard_matrix(jaccard_matrix, ax=axs[1])
    plt.subplots_adjust(bottom=0.3)
    return fig


def make_read_length_per_step(molecules: pd.DataFrame,
                              molecules_corrected: pd.DataFrame,
                              cells: pd.DataFrame,
                              cells_filtered: pd.DataFrame) -> plt.Figure:
    """Makes the subplots showing nucleotides read per molecule for each step in
    the analysis."""
    fig, axs = plt.subplots(2, 2, figsize=(12, 10), sharex=True, sharey=True)

    for this_df, ax, title in zip([molecules, molecules_corrected], axs[0],
                                  ['Molecules', 'Corrected Molecules']):
        vals = get_length_read(this_df)
        complete_reads = sum(vals == 30)
        percentage_complete = 100 * complete_reads / len(vals)
        this_text = f'There are {len(vals)} molecules. {complete_reads} have ' \
                    f'been \nread completely, which accounts for ' \
                    f'{percentage_complete:.1f}%'
        plot_discrete_histogram(vals, ax=ax, xlabel='Nucleotides Read',
                                txt=this_text,
                                title=title)

    for this_df, ax, title in zip([cells, cells_filtered], axs[1],
                                  ['Cells', 'Filtered Cells']):
        vals = get_length_read(this_df, molecules_dataframe=False)
        complete_reads = sum(vals == 30)
        percentage_complete = 100 * complete_reads / len(vals)
        this_text = f'There are {len(vals)} viral CloneID molecules. {complete_reads} have ' \
                    f'been \nread completely, which accounts for ' \
                    f'{percentage_complete:.1f}%'
        plot_discrete_histogram(vals, ax=ax, xlabel='Nucleotides Read',
                                txt=this_text,
                                title=title)

    plt.suptitle('Nucleotides Read per Molecule')
    plt.subplots_adjust(hspace=0.5)
    return fig


def make_molecules_per_cell_per_step(molecules: pd.DataFrame,
                                     molecules_corrected: pd.DataFrame,
                                     cells: pd.DataFrame,
                                     cells_filtered: pd.DataFrame) -> plt.Figure:
    """Makes the subplots showing CloneID molecules per cell for each step in
    the analysis."""
    fig, axs = plt.subplots(2, 2, figsize=(12, 10), sharex=True, sharey=True)

    for this_df, ax, title in zip([molecules, molecules_corrected], axs[0],
                                  ['Molecules', 'Corrected Molecules']):
        vals = get_clone_ids_per_cell(this_df)
        mean = np.mean(vals)
        quantiles = np.quantile(vals, [0.25, 0.5, 0.75])

        this_txt = f'There are {len(vals)} molecules. On average, there are\n' \
                   f'{mean:.2f} molecules per cell, with a median of {quantiles[1]} and \n' \
                   f'interquartile range of {quantiles[0]} - {quantiles[2]}'

        plot_discrete_histogram(vals, ax=ax, xlabel='CloneID Molecules',
                                txt=this_txt, title=title)
        ax.axvline(x=mean, color='red', alpha=0.8)
        for p in quantiles:
            ax.axvline(x=p, color='black', alpha=0.8, ls='--', lw=0.5)

    for this_df, ax, title in zip([cells, cells_filtered], axs[1],
                                  ['Cells', 'Filtered Cells']):
        vals = get_clone_ids_per_cell(this_df, molecules_dataframe=False)
        mean = np.mean(vals)
        quantiles = np.quantile(vals, [0.25, 0.5, 0.75])

        this_txt = f'There are {len(vals)} molecules. On average, there are\n' \
                   f'{mean:.2f} molecules per cell, with a median of {quantiles[1]} and \n' \
                   f'interquartile range of {quantiles[0]} - {quantiles[2]}'

        plot_discrete_histogram(vals, ax=ax, xlabel='CloneID Molecules',
                                txt=this_txt, title=title)
        ax.axvline(x=mean, color='red', alpha=0.8)
        for p in quantiles:
            ax.axvline(x=p, color='black', alpha=0.8, ls='--', lw=0.5)

    plt.suptitle('CloneID Molecules per Cell')
    plt.subplots_adjust(hspace=0.5, bottom=0.2)

    return fig


def make_molecules_per_clone_id_per_step(molecules: pd.DataFrame,
                                        molecules_corrected: pd.DataFrame,
                                        cells: pd.DataFrame,
                                        cells_filtered: pd.DataFrame) -> plt.Figure:
    """Makes the subplots showing CloneID molecules per unique CloneID for each
    step in the analysis."""
    fig, axs = plt.subplots(2, 2, figsize=(12, 10), sharex=True, sharey=True)

    for this_df, ax, title in zip([molecules, molecules_corrected], axs[0],
                                  ['Molecules', 'Corrected Molecules']):
        vals = get_molecules_per_clone_ids(this_df)
        mean = np.mean(vals)
        quantiles = np.quantile(vals, [0.25, 0.5, 0.75])

        this_txt = f'There are {len(vals)} unique CloneIDs. On average, there\n' \
                   f'are {mean:.2f} molecules per unique CloneID, with a  \n' \
                   f'median of {quantiles[1]} and interquartile range of {quantiles[0]} - {quantiles[2]}.\n' \
                   f'{sum(vals == 1)} are CloneIDs with single molecules.'

        plot_discrete_histogram(vals, ax=ax, xlabel='CloneID Molecules',
                                txt=this_txt, title=title)
        ax.axvline(x=mean, color='red', alpha=0.8)
        for p in quantiles:
            ax.axvline(x=p, color='black', alpha=0.8, ls='--', lw=0.5)

    for this_df, ax, title in zip([cells, cells_filtered], axs[1],
                                  ['Cells', 'Filtered Cells']):
        vals = get_molecules_per_clone_ids(this_df, molecules_dataframe=False)
        mean = np.mean(vals)
        quantiles = np.quantile(vals, [0.25, 0.5, 0.75])

        this_txt = f'There are {len(vals)} unique CloneIDs. On average, there\n' \
                   f'are {mean:.2f} molecules per unique CloneID, with a  \n' \
                   f'median of {quantiles[1]} and interquartile range of {quantiles[0]} - {quantiles[2]}. \n' \
                   f'{sum(vals == 1)} are CloneIDs with single molecules.'

        plot_discrete_histogram(vals, ax=ax, xlabel='CloneID Molecules',
                                txt=this_txt, title=title)
        ax.axvline(x=mean, color='red', alpha=0.8)
        for p in quantiles:
            ax.axvline(x=p, color='black', alpha=0.8, ls='--', lw=0.5)

    plt.suptitle('CloneID Molecules per Unique CloneID in Dataset')
    plt.subplots_adjust(hspace=0.6, bottom=0.2)

    return fig


def make_unique_clone_ids_per_cell_per_step(molecules: pd.DataFrame,
                                           molecules_corrected: pd.DataFrame,
                                           cells: pd.DataFrame,
                                           cells_filtered: pd.DataFrame) -> plt.Figure:
    """Makes the subplots showing unique CloneIDs per cell for each step in the
    analysis."""
    fig, axs = plt.subplots(2, 2, figsize=(12, 10), sharex=True, sharey=True)

    for this_df, ax, title in zip([molecules, molecules_corrected], axs[0],
                                  ['Molecules', 'Corrected Molecules']):
        vals = get_unique_clone_ids_per_cell(this_df)
        mean = np.mean(vals)
        quantiles = np.quantile(vals, [0.25, 0.5, 0.75])

        this_txt = f'There are {len(vals)} cells. On average, they have {mean:.2f}\n' \
                   f'unique CloneIDs per cell, with a median of {quantiles[1]}\n' \
                   f'and interquartile range of {quantiles[0]} - {quantiles[2]}.\n' \
                   f'{sum(vals == 1)} cells have a single unique CloneID.'

        plot_discrete_histogram(vals, ax=ax, xlabel='CLoneID Molecules',
                                txt=this_txt, title=title)
        ax.axvline(x=mean, color='red', alpha=0.8)
        for p in quantiles:
            ax.axvline(x=p, color='black', alpha=0.8, ls='--', lw=0.5)

    for this_df, ax, title in zip([cells, cells_filtered], axs[1],
                                  ['Cells', 'Filtered Cells']):
        vals = get_unique_clone_ids_per_cell(this_df, molecules_dataframe=False)
        mean = np.mean(vals)
        quantiles = np.quantile(vals, [0.25, 0.5, 0.75])

        this_txt = f'There are {len(vals)} cells. On average, they have {mean:.2f}\n' \
                   f'unique CloneIDs per cell, with a median of {quantiles[1]}\n' \
                   f'and interquartile range of {quantiles[0]} - {quantiles[2]}.\n' \
                   f'{sum(vals == 1)} cells have a single unique CloneID.'

        plot_discrete_histogram(vals, ax=ax, xlabel='Unique CloneIDs',
                                txt=this_txt, title=title)
        ax.axvline(x=mean, color='red', alpha=0.8)
        for p in quantiles:
            ax.axvline(x=p, color='black', alpha=0.8, ls='--', lw=0.5)

    plt.suptitle('Unique CloneIDs per Cell')
    plt.subplots_adjust(hspace=0.6, bottom=0.2)

    return fig


def make_hamming_distance_per_step(molecules: pd.DataFrame,
                                   molecules_corrected: pd.DataFrame,
                                   cells: pd.DataFrame,
                                   cells_filtered: pd.DataFrame) -> plt.Figure:
    """Makes the subplots showing Hamming distance between all CloneIDs in the
    dataset for each step in the analysis."""
    fig, axs = plt.subplots(2, 2, figsize=(12, 10), sharex=True, sharey=True)

    for this_df, ax, title in zip([molecules, molecules_corrected], axs[0],
                                  ['Molecules', 'Corrected Molecules']):
        hamming_distance_histogram(this_df, ax=ax)
        ax.set_title(title)

    for this_df, ax, title in zip([cells, cells_filtered], axs[1],
                                  ['Cells', 'Filtered Cells']):
        hamming_distance_histogram(this_df, ax=ax)
        ax.set_title(title)

    plt.suptitle('Hamming Distance between all CloneIDs in the Dataset')
    plt.subplots_adjust(hspace=0.1)
    return fig


def make_qc_report(output_dir: Path, pdf_dir: Path,
                   plot_jaccard: bool=False,
                   plot_hamming: bool=False):
    """Load data from trex analysis and make a pdf report.

    Parameters
    ----------
    output_dir: pathlib.Path
        Points to the folder containing the output from TREX
    pdf_dir: pathlib.Path
        Points to the path where the pdf report should be saved
    plot_jaccard: bool; Default: False
        Whether jaccard similarity should be calculated pairwise between cells
        and the matrix and histogram plotted
    plot_hamming: bool; Default: False
        Whether Hamming distance between all detected CloneIDs should be
        calculated and the histogram plotted in a per-step basis."""
    logger.info("Loading reads")
    reads = load_reads(output_dir)
    logger.info("Loading molecules")
    molecules = load_molecules(output_dir)
    logger.info("Loading molecules corrected")
    molecules_corrected = load_molecules_corrected(output_dir)
    logger.info("Loading cells")
    cells = load_cells(output_dir, filtered=False)
    logger.info("Loading cells filtered")
    cells_filtered = load_cells(output_dir, filtered=True)
    logger.info("Loading clones")
    clones = load_clone_ids(output_dir)

    with PdfPages(pdf_dir) as pp:
        # Overall quality plots
        logger.info("Plotting clone size histogram")
        fig = make_clone_size_histogram(clones)
        pp.savefig(fig)
        plt.close()

        logger.info("Plotting unique CloneID per clone histogram")
        fig = make_unique_clone_ids_per_clone(clones, cells_filtered)
        pp.savefig(fig)
        plt.close()

        logger.info("Plotting unique CloneID per cell histogram")
        fig = make_unique_clone_ids_per_cell(cells_filtered)
        pp.savefig(fig)
        plt.close()

        if plot_jaccard:
            logger.info("Calculating and plotting Jaccard similarities")
            fig = make_jaccard_similarity_plots(output_dir)
            pp.savefig(fig)
            plt.close()

        logger.info("Plotting reads per molecule histogram")
        fig = make_reads_per_molecule(reads)
        pp.savefig(fig)
        plt.close()

        # per step plots
        logger.info("Plotting read length per step histograms")
        fig = make_read_length_per_step(molecules, molecules_corrected,
                                        cells, cells_filtered)
        pp.savefig(fig)
        plt.close()

        if plot_hamming:
            logger.info("Plotting Hamming distance per step histograms")
            fig = make_hamming_distance_per_step(molecules, molecules_corrected,
                                                 cells, cells_filtered)
            pp.savefig(fig)
            plt.close()

        logger.info("Plotting molecules per cell per step histograms")
        fig = make_molecules_per_cell_per_step(molecules, molecules_corrected,
                                               cells, cells_filtered)
        pp.savefig(fig)
        plt.close()

        logger.info("Plotting molecules per CloneID per step histograms")
        fig = make_molecules_per_clone_id_per_step(molecules,
                                                  molecules_corrected,
                                                  cells, cells_filtered)
        pp.savefig(fig)
        plt.close()

        logger.info("Plotting unique CloneIDs per cell per step histograms")
        fig = make_unique_clone_ids_per_cell_per_step(molecules,
                                                     molecules_corrected,
                                                     cells, cells_filtered)
        pp.savefig(fig)
        plt.close()


def main(args):
    setup_logging(debug=args.debug)

    for output_dir in args.path:
        if not output_dir.exists():
            raise CommandLineError(
                f"Output directory '{output_dir}' does not exist")

        add_file_logging(output_dir / "log.txt")
        logger.info(f"Trex {__version__}")
        logger.info("Command line arguments: %s", " ".join(sys.argv[1:]))

        pdf_dir = output_dir / 'quality_report.pdf'

        make_qc_report(output_dir, pdf_dir,
                       plot_jaccard=args.plot_jaccard_matrix,
                       plot_hamming=args.plot_hamming_distance)
