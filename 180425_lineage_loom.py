"""
Description: Program for the extraction and filtering of random barcodes from single-cell sequencing data

Preparation: Program processes cell ranger output files. Run cell ranger before. Follow instructions => cellranger_instructions.sh

Run: Run program in cellranger 'outs' directory OR indicate path to 'outs'-directory via --path flag
"""

import pysam
import os.path
import argparse
import numpy as np
from collections import Counter
from collections import defaultdict
import operator


__author__ = 'leonie.von.berlin@stud.ki.se'


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--genome-name',
        help='name of the genome as indicated in cell ranger count run with the flag --genome. Default %(default)s',
        default='hg38_Tomato-N')
    parser.add_argument('--chromosome', '--chr',
        help="barcode chromosome name as indicated in .fasta file. Default: %(default)s. See cellranger_instructions.sh",
        default='chrTomato-N')
    parser.add_argument('-p', '--path',
        help='path to cell ranger "outs" directory. Default: current directory',
        default=os.getcwd())
    parser.add_argument('-n', '--name',
        help='name of the run and directory created by program. Default: lineage_run',
        default='lineage_run')
    parser.add_argument('-s', '--start',
        help='Position of first base INSIDE the barcode (with first base of sequence on position 0). Default: %(default)s',
        type=int, default=694)
    parser.add_argument('-e', '--end',
        help='Position of last base INSIDE the barcode (with first base of sequence on position 0). Default: %(default)s',
        type=int, default=724)
    parser.add_argument('-m', '--min-length',
        help='Minimum number of bases a barcode must have. Default: 10', type=int, default=10)
    parser.add_argument('--hamming',
        help='Minimum hamming distance allowed for two barcodes to be called similar. Default: %(default)s',
        type=int, default=4)
    parser.add_argument('-l', '--loom',
        help='If given, create loom-file from cell ranger and barcode data. File will have the same name as the run',
        action='store_true')
    return parser.parse_args()


def read_cellid_barcodes(path):
    """
    Read barcodes.tsv, which contains a list of corrected and approved cellIDs like this:

    AAACCTGAGCGACGTA-1
    AAACCTGCATACTCTT-1
    """
    with open(path) as f:
        ids = []
        for line in f:
            line = line.strip('\n')
            ids.append(line)
    return set(ids)


def read_bam(bam_path, output_bam_path, chr_name, cell_ids, start_bc, end_bc):
    """
    bam_path -- path to input BAM file
    output_bam_path -- path to an output BAM file. All reads on the chromosome that have the
        required tags are written to this file
    """
    # Opening required files: possorted_genome_bam.bam contains all aligned reads in bam format,
    alignment_file = pysam.AlignmentFile(bam_path)
    out_bam = pysam.AlignmentFile(output_bam_path, 'wb', template=alignment_file)

    len_bc = end_bc - start_bc - 1

    # Fetches those reads aligning to the artifical, barcode-containing chromosome
    read_col = []
    for read in alignment_file.fetch(chr_name):
        # Skip reads without cellID or UMI
        if not read.has_tag('CB') or not read.has_tag('UB'):
            continue
        # Filters out reads that have not approved cellIDs
        cell_id = read.get_tag('CB')
        if cell_id not in cell_ids:
            continue
        # Collects information from the bam-entry of the read
        # writes a new bam_file with only those reads aligning to barcode-chromosome. See chr_name_entries.bam
        out_bam.write(read)
        barcode = ''

        queryseq = read.query_sequence
        query_align_end = read.query_alignment_end
        query_align_start = read.query_alignment_start
        ref_start = read.reference_start
        len_read = read.infer_query_length()
        start_check = start_bc - len_read
        end_check = start_check + len_bc + 2

        # Extracts barcodes based on the alignment-pair list (gives position of read and corresponding reference position)
        for query_pos, ref_pos in read.get_aligned_pairs():
            if ref_pos is None:  # part of read that doesn't align to ref
                if start_check < ref_start < end_check and query_align_end <= \
                        query_pos:  # takes soft clipped bases from the end (downstream of query aligned seq) of those reads that have the barcode at the end
                    if start_bc < (ref_start + query_pos) < end_bc:  # makes sure that the soft clipped base is IN the barcode and not up-/downstream of it
                        barcode += queryseq[query_pos]  # adds soft clipped base of barcode to barcode-string
                elif query_align_start > query_pos and start_bc < (
                        (ref_start - len_bc) + query_pos) < end_bc:  # takes soft clipped bases from the beginning (upstream of query aligned seq) of those reads that have the barcode at the beginning
                    barcode += queryseq[query_pos]
            elif start_bc < ref_pos < end_bc:  # part of read that aligns to barcode area
                if query_pos is None:  # a deletion in the read in a barcode postion
                    barcode += '0'  # deletion in the barcode are indicated with 0
                else:
                    barcode += queryseq[query_pos]  # takes base in barcode position and adds to barcode string

        if barcode == '':
            barcode = len_bc * '-'  # sequences with no barcode are indicated with len_bc*-

        # sequences containing only a part of the barcode have other positions upstream or downstream filled with -
        if len(barcode) < len_bc:
            if start_check < ref_start < end_check:
                barcode = barcode + (len_bc - len(barcode)) * '-'
            else:
                barcode = (len_bc - len(barcode)) * '-' + barcode
        read_col.append((cell_id, read.get_tag('UB'), barcode))

    # sorts reads first based on UMI, then CellID, then barcode
    sorted_reads = sorted(read_col, key=lambda read: (read[1], read[0], read[2]))
    alignment_file.close()
    out_bam.close()
    return sorted_reads


def main():
    args = parse_arguments()

    # Loading the user or default based arguments
    genome_name = args.genome_name
    chr_name = args.chromosome
    pwd = args.path
    run_name = args.name
    start_bc = args.start - 1
    end_bc = args.end
    len_bc = end_bc - start_bc - 1
    minlen_bc = args.min_length - 1
    minham = args.hamming + 1

    # Creating an output folder named after user or default defined run-name in current working directory
    os.makedirs(run_name)

    # Opening output files in the recently created output folder
    read_file = open(os.path.join(run_name, 'reads.txt'), 'w+')
    mol_file = open(os.path.join(run_name, 'molecules.txt'), 'w+')
    cell_file = open(os.path.join(run_name, 'cells.txt'), 'w+')
    cellfilt_file = open(os.path.join(run_name, 'cells_filtered.txt'), 'w+')
    groups_file = open(os.path.join(run_name, 'groups.txt'), 'w+')

    # Writing the first commented line into output files
    read_file.write(
        '#Each output line corresponds to one read and has the following style: CellID\tUMI\tBarcode' + '\n' + '# dash (-) = barcode base outside of read, 0 = deletion in barcode sequence (position unknown)' + '\n')
    mol_file.write(
        '#Each output line corresponds to one molecule and has the following style: CellID\tUMI\tBarcode' + '\n' + '# dash (-) = barcode base outside of read, 0 = deletion in barcode sequence (position unknown)' + '\n')
    cell_file.write(
        '#Each output line corresponds to one cell and has the following style: CellID\tBarcode1\tCount1\tBarcode2\tCount2...' + '\n' + '# dash (-) = barcode base outside of read, 0 = deletion in barcode sequence (position unknown)' + '\n')
    cellfilt_file.write(
        '#Each output line corresponds to one cell and has the following style: CellID\t:\tBarcode1\tCount1\tBarcode2\tCount2...' + '\n' + '# dash (-) = barcode base outside of read, 0 = deletion in barcode sequence (position unknown)' + '\n')
    groups_file.write(
        '#Each output line corresponds to one barcode group (clone) and has the following style: Barcode\t:\tCellID1\tbarcode-count1\tCellID2\tbarcode-count2...' + '\n' + '# dash (-) = barcode base outside of read, 0 = deletion in barcode sequence (position unknown)' + '\n')

    ####################################################################################
    ###          PART I + II: Barcode extraction and reads construction              ###
    ####################################################################################

    #  1. Extracts reads aligning to barcode-chromosome, 2. extracts barcodes, UMIs and cellIDs
    #   from reads, 3. outputs UMI-sorted reads with barcodes

    cell_ids = read_cellid_barcodes(os.path.join(pwd, 'filtered_gene_bc_matrices', genome_name, 'barcodes.tsv'))

    read_sorted = read_bam(os.path.join(pwd, 'possorted_genome_bam.bam'), os.path.join(run_name, chr_name + '_entries.bam'), chr_name, cell_ids, start_bc, end_bc)

    for read in read_sorted:
        print(*read[:3], sep='\t', file=read_file)

    ########################################################################################
    ###                       Part III: Molecule construction                            ###
    ########################################################################################

    # 1. Forms groups of reads with identical CellIDs and UMIs => belong to one molecule,
    #   2. forms consensus sequence of all barcodes of one group, 3. outputs molecules and
    #   corresponding CellIDs/UMIs

    # extracts the start and end index of groups with identical UMI and cellID
    group_pos = [0]
    for i in range(0, len(read_sorted) - 1):
        if not (read_sorted[i][1] == read_sorted[i + 1][1] and read_sorted[i][0] == read_sorted[i + 1][0]):
            group_pos.append(i + 1)

    # creates a list of sublists, each representing one group of reads with identical UMI/cellID
    groups = []
    for i in range(0, len(group_pos) - 1):
        groups.append(read_sorted[group_pos[i]:group_pos[i + 1]])
    groups.append(read_sorted[group_pos[-1]:(len(read_sorted) + 1)])

    # converts each sequence of each group that is greater than 1 into a binary code, sums up binary code of all sequences, calculates max value for each position and outputs consensus sequence
    letters = np.array(['A', 'C', 'G', 'T', '-', '0'])

    mol_col = list()
    for group in groups:  # takes out each group
        if len(group) > 1:  # filters out groups that contain only one read
            consens_np = np.zeros([len_bc, 6], dtype='float16')
            for j in range(0, len(group)):  # takes out each sequence from a group
                align = np.zeros([len_bc, 6], dtype='float16')
                for (l, s) in enumerate(group[j][2]):  # takes out each base from sequence
                    # turns each base into a number and position in numpy array
                    if s == 'A':
                        align[l, 0] = 1
                    elif s == 'C':
                        align[l, 1] = 1
                    elif s == 'G':
                        align[l, 2] = 1
                    elif s == 'T':
                        align[l, 3] = 1
                    elif s == '-':
                        align[l, 4] = 0.1
                    elif s == '0':
                        align[l, 5] = 0.1
                consens_np = consens_np + align  # sums up numbers of each position
            bin_consens = np.argmax(align,
                axis=1)  # calculates base with maximum count for each position
            x = letters[bin_consens]  # converts maximum counts into consensus sequence
            consensus = ''.join(x)

            mol_col.append((group[0][0], group[0][1], consensus))
        else:
            mol_col.append((group[0][0], group[0][1], group[0][2]))
    # calling mol_col will give a list of all molecules with corresponding UMIs/cellIDs. See molecules.txt

    # sorts molecules based on cellIDs, then barcodes, then UMIs
    mol_sorted = sorted(mol_col, key=lambda mol: (mol[0], mol[2], mol[1]))

    for mol in mol_sorted:
        mol_file.write(mol[0] + '\t' + mol[1] + '\t' + mol[2] + '\n')

    ########################################################################################
    ###                          Part IV: Cell construction                              ###
    ########################################################################################

    # 1. Forms groups of molecules (with set barcode minimum length) that have identical cellIDs
    #  => belong to one cell, 2. counts number of appearances of each barcode in each group,
    #   3. starting from the barcode with the lowest count, compares to barcodes starting with
    #   the highest counts of a group and calculates hamming distance. If distance is below threshold,
    #   the two barcodes and counts are merged. Repetition until no barcodes with hamming distance
    #   below threshold can be found (note that this way of merging is greedy),
    #   4. Outputs for each cells all its barcodes and corresponding counts

    barcode_list = []
    cellid_list = []
    umi_list = []

    for mol in mol_sorted:
        cellid = mol[0]
        umi = mol[1]
        barcode = mol[2]
        pure_bc = barcode.strip('-')
        pure_bc0 = barcode.strip('0')
        if len(pure_bc) > minlen_bc and len(
                pure_bc0) > minlen_bc:  # filters out barcodes shorter than min length
            barcode_list.append(barcode)
            cellid_list.append(cellid)

    # extracts the start and end index of groups with identical cellID
    group_pos = [0]
    for i in range(0, len(cellid_list) - 1):
        if cellid_list[i] == cellid_list[i + 1]:
            pass
        else:
            group_pos.append(i + 1)

    # creates a list of sublists, each representing one group of molecules with identical cellID
    cellid_grp = []
    barcode_grp = []
    for i in range(0, len(group_pos) - 1):
        cellid_grp.append(cellid_list[group_pos[i]:group_pos[i + 1]])
        barcode_grp.append(barcode_list[group_pos[i]:group_pos[i + 1]])
    cellid_grp.append(cellid_list[group_pos[-1]:(len(cellid_list) + 1)])
    barcode_grp.append(barcode_list[group_pos[-1]:(len(barcode_list) + 1)])

    # merges barcodes and counts below hamming distance
    cell_col = []
    found = False
    for group in cellid_grp:
        cellid = group[0]
        bcgrp = barcode_grp[cellid_grp.index(group)]
        bc_counts = Counter(bcgrp)  # counts the appearances of different barcodes in each group
        results = defaultdict(int)
        mc = sorted(bc_counts.most_common(),
            key=lambda x: -len(x[0].strip('-')))  # sorts barcodes based on counts
        while True:
            x, n = mc.pop(-1)  # takes out and removew barcode with lowest count from list
            if len(
                    mc) == 0:  # or '0' in x: #if barcode is the last in the list or it contains insertions/deletions (cannot be compared) just keeps barcode without merging
                results[x] += n
                break
            for i, m in mc:  # goes through remaining barcodes in list
                hamming = 0
                overlapp_count = 0
                for l, k in zip(x, i):
                    if l != '-' and k != '-':  # only compares base-containing and not empty position
                        overlapp_count = overlapp_count + 1  # counts the overlap of two barcodes
                        if l != k:
                            hamming = hamming + 1  # calculates hamming distance based on the similarity of each base-pair
                if hamming < minham and overlapp_count != 0:  # filters out barcode-pairs with hamming distance below set threshold or with no overlapp
                    if len(i.strip('-')) == len_bc:  # only full barcodes are merged with other groups
                        results[i] += n
                        found = True
                        break
                    else:
                        results[x] += n
                        found = True
                        break

            if not found:  # barcodes that never undergo the hamming distance threshold, are not merged
                results[x] += n
            else:
                found = False

        cell_col.append(cellid)
        cell_col.append(results)
        cell_file.write(cellid + '\t:\t')
        results_sorted = sorted(results, key=lambda x: -results[x])
        for key in results_sorted:
            cell_file.write(key + '\t' + str(results[key]) + '\t')
        cell_file.write('\n')
    cell_col_copy = cell_col

    # calling cell_col_copy will give all cells and their unfiltered barcodes+counts. See cells.txt
    # calling cell_col will give all cells and filtered barcodes. See below.


    ########################################################################################
    ###                    Part V + VI: Barcodes filtering and grouping                  ###
    ########################################################################################

    # 1. Filters barcodes according to two criteria: 1. Barcodes that have only a count of one
    #   and can be found in another cell are most likely results of contamination and are
    #   removed, 2. Barcodes that have only a count of one and are also only based on one
    #   read are also removed
    # 2. Groups cells with same barcodes that most likely stem from one clone. Outputs a file
    #   with all clones and cellIDs belonging to each clone


    bc_all = list()
    cellids = list()
    for i in range(1, len(cell_col), 2):
        for key in cell_col[i]:
            cellids.append(cell_col[i - 1])
            bc_all.append(key)
            bc_all.append(cell_col[i][key])

    # filters out barcodes with a count of one that appear in another cell
    for i in range(1, len(cell_col), 2):
        dict_cp = dict(cell_col[i])
        for key in dict_cp:
            if key in cell_col[i]:
                if cell_col[i][key] == 1:  # filters out barcodes that are only based on one molecule
                    if bc_all.count(
                            key) > 1:  # filters out barcodes that appear more than once in the whole list
                        del cell_col[i][key]  # removes barcodes that meet both criteria
                    else:
                        for j in groups:  # groups is a list of groups of reads with identical UMIs/cellIDs (see part II)
                            if (cell_col[i - 1] == j[0][
                                0]):  # if cellID is identical to cellID in groups, it keeps the group
                                if len(
                                        j) == 1:  # filters out those barcodes that are based on only one read => group has only a length of one
                                    if key in cell_col[i]:
                                        del cell_col[i][key]  # deletes those barcodes

    # calling cell_col will give a list of all cellIDs and only the filtered barcodes

    groups_dict = dict()
    for i in range(0, len(cell_col), 2):
        sort_d = sorted(cell_col[i + 1].items(), key=operator.itemgetter(1))
        sort_d.reverse()
        if len(sort_d) != 0:
            cellfilt_file.write(cell_col[i] + '\t:\t')
            for tup in sort_d:
                cellfilt_file.write(tup[0] + '\t' + str(tup[1]) + '\t')
            cellfilt_file.write('\n')
        # cellIDs and filtered barcodes can be found in cells_filtered.txt

        # forms groups of cells with same barcode
        for key in cell_col[i + 1]:
            if not key in groups_dict:  # creates a new group if not existing yet. Saves cellID in a list
                groups_dict.update({key: [cell_col[i], cell_col[i + 1][key]]})
            else:  # updates an existing group by appending cellID to the cellID list
                groups_dict[key].append(cell_col[i])
                groups_dict[key].append(cell_col[i + 1][key])

    groupsdict_s = sorted(groups_dict.items(), key=operator.itemgetter(0))
    for i in range(0, len(groupsdict_s)):
        groups_file.write(groupsdict_s[i][0] + '\t:\t')
        for j in range(0, len(groupsdict_s[i][1]), 2):
            groups_file.write(groupsdict_s[i][1][j] + '\t' + str(groupsdict_s[i][1][j + 1]) + '\t')
        groups_file.write('\n')
    # in groups.txt all barcodes and their corresponding cellIDs can be found


    ########################################################################################
    ###                        Part VII: Output in loom format                           ###
    ########################################################################################
    # An optional feature that 1. creates a loom-file from cellranger output data, 2. adds
    # the barcode results to the loom-file

    def write_loom():
        bc_dict = {'1': [], '2': [], '3': [], '4': [], '5': [], '6': []}
        cnt_dict = {'1': [], '2': [], '3': [], '4': [], '5': [], '6': []}
        cellid1 = []

        # brings the barcode data into a format where the most abundant barcode of the cells are in
        # one list, the second most abundant in another and so on. The same with counts
        for i in range(0, len(cell_col), 2):
            sort_d = sorted(cell_col[i + 1].items(), key=operator.itemgetter(1))
            sort_d.reverse()
            if len(sort_d) != 0:
                cellid1.append(cell_col[i])
                for j in range(0, 6):
                    k = j + 1
                    if j <= len(sort_d) - 1:
                        bc_dict[str(k)].append(sort_d[j][0])
                        cnt_dict[str(k)].append(sort_d[j][1])
                    else:
                        bc_dict[str(k)].append('-')
                        cnt_dict[str(k)].append(0)

                    # creates the loom file based on cellranger output files
        import loompy

        loom_name = os.path.basename(pwd[:-5])
        pwd_loom = os.path.join(run_name, loom_name + '.loom')
        if not os.path.exists(pwd_loom):
            loompy.create_from_cellranger(pwd[:-5], run_name)
        # connects to the just created loom file in order to modify it
        ds = loompy.connect(pwd_loom)
        # gets a list of all cellIDs appearing in the loom file
        all_cellIDs = ds.ca.CellID

        # brings barcode data into correct format for loom file. Array must have same shape as all_cellIDs
        bc_fulldict = {'1': [], '2': [], '3': [], '4': [], '5': [], '6': []}
        cnt_fulldict = {'1': [], '2': [], '3': [], '4': [], '5': [], '6': []}
        for id1 in all_cellIDs:
            found = False
            for id2 in cellid1:
                if id1[(len(loom_name) + 1):] == id2:
                    found = True
                    index = cellid1.index(id2)
                    bc_fulldict['1'].append(bc_dict['1'][index])
                    bc_fulldict['2'].append(bc_dict['2'][index])
                    bc_fulldict['3'].append(bc_dict['3'][index])
                    bc_fulldict['4'].append(bc_dict['4'][index])
                    bc_fulldict['5'].append(bc_dict['5'][index])
                    bc_fulldict['6'].append(bc_dict['6'][index])

                    cnt_fulldict['1'].append(cnt_dict['1'][index])
                    cnt_fulldict['2'].append(cnt_dict['2'][index])
                    cnt_fulldict['3'].append(cnt_dict['3'][index])
                    cnt_fulldict['4'].append(cnt_dict['4'][index])
                    cnt_fulldict['5'].append(cnt_dict['5'][index])
                    cnt_fulldict['6'].append(cnt_dict['6'][index])
                    break

            if not found:
                bc_fulldict['1'].append('-')
                bc_fulldict['2'].append('-')
                bc_fulldict['3'].append('-')
                bc_fulldict['4'].append('-')
                bc_fulldict['5'].append('-')
                bc_fulldict['6'].append('-')

                cnt_fulldict['1'].append(0)
                cnt_fulldict['2'].append(0)
                cnt_fulldict['3'].append(0)
                cnt_fulldict['4'].append(0)
                cnt_fulldict['5'].append(0)
                cnt_fulldict['6'].append(0)

        # adds the barcode information to the loom file
        ds.ca['linBarcode_1'] = np.array(bc_fulldict['1'], dtype='S%r' % len_bc)
        ds.ca['linBarcode_2'] = np.array(bc_fulldict['2'], dtype='S%r' % len_bc)
        ds.ca['linBarcode_3'] = np.array(bc_fulldict['3'], dtype='S%r' % len_bc)
        ds.ca['linBarcode_4'] = np.array(bc_fulldict['4'], dtype='S%r' % len_bc)
        ds.ca['linBarcode_5'] = np.array(bc_fulldict['5'], dtype='S%r' % len_bc)
        ds.ca['linBarcode_6'] = np.array(bc_fulldict['6'], dtype='S%r' % len_bc)

        # adds the count information to the loom file
        ds.ca['linBarcode_count_1'] = np.array(cnt_fulldict['1'], dtype=int)
        ds.ca['linBarcode_count_2'] = np.array(cnt_fulldict['2'], dtype=int)
        ds.ca['linBarcode_count_3'] = np.array(cnt_fulldict['3'], dtype=int)
        ds.ca['linBarcode_count_4'] = np.array(cnt_fulldict['4'], dtype=int)
        ds.ca['linBarcode_count_5'] = np.array(cnt_fulldict['5'], dtype=int)
        ds.ca['linBarcode_count_6'] = np.array(cnt_fulldict['6'], dtype=int)

        ds.close()


    if args.loom:
        write_loom()

    # closes all opened files
    cellfilt_file.close()
    cell_file.close()
    read_file.close()
    mol_file.close()
    groups_file.close()

    # finished!
    print('Run completed!')


if __name__ == '__main__':
    main()
