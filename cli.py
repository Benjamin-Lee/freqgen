import click
from click_default_group import DefaultGroup
from Bio import SeqIO
import Bio.Data.CodonTable
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
import yaml

from freqgen import k_mer_frequencies, codon_frequencies, amino_acid_seq
from freqgen import generate as _generate

@click.group(cls=DefaultGroup, default='generate', default_if_no_args=True)
def freqgen():
    pass

@freqgen.command(help="Featurize a FASTA file")
@click.argument('filepath', click.Path(exists=True, dir_okay=False))
@click.option('-k', multiple=True, type=int, help="Values of k to featurize the seqs for. May be repeated.")
@click.option("-c", "--codon-usage", is_flag=True, help="Whether to include a codon frequency featurization.")
@click.option("-o", '--output', type=click.Path(exists=False, dir_okay=False), help="The output file.")
def featurize(filepath, k, codon_usage, output):
    # get the sequences as strs
    seqs = []
    with open(filepath, "r") as handle:
        for seq in SeqIO.parse(handle, "fasta"):
            seq = str(seq.seq)
            seqs.append(seq)

    result = {_k: k_mer_frequencies(seqs, _k, include_missing=True) for _k in k}

    # get the codon usage frequencies
    if codon_usage:
        for seq in seqs:
            if len(seq) % 3 != 0:
                raise ValueError("Cannot calculate codons for sequence whose length is not divisible by 3")
        result["codons"] = codon_frequencies("".join(seqs))

    if output:
        yaml.dump(result, open(output, "w+"), default_flow_style=False)
        return
    print(yaml.dump(result, default_flow_style=False))

@freqgen.command(help="Generate an amino acid sequence from FASTA")
@click.argument('filepath', click.Path(exists=True, dir_okay=False))
@click.option("--mode", type=click.Choice(["freq", "seq"]), help="Whether to use the exact AA seq or its frequencies. Defaults to freq.", default="freq")
@click.option("-t", "--trans-table", type=int, default=11, help="The translation table to use. Defaults to 11, the standard genetic code.")
@click.option("-l", "--length", type=int, help="The length of the AA sequence (excluding stop codon) to generate if --mode=freq.")
@click.option("-s", "--stop-codon", is_flag=True, default=True, help="Whether to include a stop codon. Defaults to true.")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Whether to print final result if outputting to file. Defaults to false.")
@click.option("-o", '--output', type=click.Path(exists=False, dir_okay=False))
def aa(filepath, mode, trans_table, length, stop_codon, output, verbose):

    # translate the DNA seq, if using exact AA seq
    if mode == "seq":
        try:
            aa_seq = SeqIO.read(filepath, "fasta").seq.translate(table=trans_table)
        except Bio.Data.CodonTable.TranslationError:
            print("Sequence is not able to be translated! Is it already an amino acid sequence?")
            return
        if "*" in aa_seq:
            aa_seq.replace("*", "")

    elif mode == "freq":
        seqs = []
        # extract the sequences from the reference set
        with open(filepath, "r") as handle:
            for record in SeqIO.parse(handle, "fasta"):
                try:
                    aa_seq = str(record.seq.translate(table=trans_table)) # for DNA sequences, translate them
                except Bio.Data.CodonTable.TranslationError:
                    aa_seq = str(record.seq) # for amino acid sequences, just get the string
                seqs.append(aa_seq)

        # make them into one big sequence
        seqs = "".join(seqs)
        seqs.replace("*", "")

        # generate a new sequence of the right length
        aa_seq = amino_acid_seq(length, k_mer_frequencies(seqs, 1))

    if stop_codon:
        aa_seq += "*"

    # output to the file
    if output:
        with open(output, "w+") as output_handle:
            if not isinstance(aa_seq, Seq):
                aa_seq = Seq(aa_seq)
            SeqIO.write(SeqRecord(aa_seq, id="Generated by Freqgen from " + str(filepath), description=""), output_handle, "fasta")

    if verbose or not output:
        print(aa_seq)

@freqgen.command(help="Generate a new DNA sequence with matching features")
@click.option("-a", '--aa-seq', type=click.Path(exists=True, dir_okay=False))
@click.option("-f", '--freqs', type=click.Path(exists=True, dir_okay=False))
@click.option("-v", "--verbose", is_flag=True, default=False, help="Whether to show optimization progress. Defaults to false.")
@click.option("-i", type=int, default=50, help="How many generations to stop after no improvement. Defaults to 50.")
@click.option("-p", type=int, default=100, help="Population size. Defaults to 100.")
@click.option("-m", type=float, default=0.3, help="Mutation rate. Defaults to 0.3.")
@click.option("-c", type=float, default=0.8, help="Crossover rate. Defaults to 0.8.")
@click.option("-t", "--trans-table", type=int, default=11, help="The translation table to use. Defaults to 11, the standard genetic code.")
@click.option("-o", '--output', type=click.Path(exists=False, dir_okay=False))
def generate(aa_seq, freqs, verbose, i, p, m, c, trans_table, output):
    optimized = _generate(yaml.load(open(freqs)),
                          SeqIO.read(aa_seq, "fasta").seq,
                          verbose=verbose,
                          max_gens_since_improvement=i,
                          population_size=p,
                          mutation_probability=m,
                          crossover_probability=c,
                          genetic_code=trans_table)
    if verbose:
        print("Optimized sequence:", optimized)
    if output:
        with open(output, "w+") as output_handle:
            SeqIO.write(SeqRecord(Seq(optimized), id="Optimized by Freqgen", description=""), output_handle, "fasta")
