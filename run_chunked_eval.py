import click
import torch.cuda
from mteb import MTEB
from transformers import AutoModel, AutoTokenizer

from chunked_pooling.chunked_eval_tasks import *
from chunked_pooling.wrappers import load_model

DEFAULT_CHUNKING_STRATEGY = 'fixed'
DEFAULT_CHUNK_SIZE = 256
DEFAULT_N_SENTENCES = 5
BATCH_SIZE = 1
DEFAULT_LONG_LATE_CHUNKING_OVERLAP_SIZE = 256
DEFAULT_LONG_LATE_CHUNKING_EMBED_SIZE = 8192 # set to 0 to disable long late chunking


@click.command()
@click.option(
    '--model-name',
    default='jinaai/jina-embeddings-v2-small-en',
    help='The name of the model to use.',
)
@click.option(
    '--strategy',
    default=DEFAULT_CHUNKING_STRATEGY,
    help='The chunking strategy to be applied.',
)
@click.option(
    '--task-name', default='SciFactChunked', help='The evaluation task to perform.'
)
@click.option(
    '--eval-split', default='test', help='The name of the evaluation split in the task.'
)
@click.option(
    '--chunking-model',
    default=None,
    required=False,
    help='The name of the model used for semantic chunking.',
)
@click.option(
    '--truncate-max-length',
    default=None,
    type=int,
    help='Maximum number of tokens; By default, no truncation is done. If defined, Long Late Chunking algorithm is disabled.',
)
@click.option(
    '--chunk-size',
    default=DEFAULT_CHUNK_SIZE,
    type=int,
    help='Number of tokens per chunk for fixed strategy.',
)
@click.option(
    '--n-sentences',
    default=DEFAULT_N_SENTENCES,
    type=int,
    help='Number of sentences per chunk for sentence strategy.',
)
@click.option(
    '--long-late-chunking-embed-size',
    default=DEFAULT_LONG_LATE_CHUNKING_EMBED_SIZE,
    type=int,
    help='Token length of the embeddings that come before/after soft boundaries (i.e. overlapping embeddings). Above zero, overlap is used between neighbouring embeddings.',
)
@click.option(
    '--long-late-chunking-overlap-size',
    default=DEFAULT_LONG_LATE_CHUNKING_OVERLAP_SIZE,
    type=int,
    help='Number of tokens per chunk for fixed strategy.',
)
def main(
    model_name,
    strategy,
    task_name,
    eval_split,
    chunking_model,
    truncate_max_length,
    chunk_size,
    n_sentences,
    long_late_chunking_embed_size,
    long_late_chunking_overlap_size
):
    try:
        task_cls = globals()[task_name]
    except:
        raise ValueError(f'Unknown task name: {task_name}')
    
    if truncate_max_length is not None and (long_late_chunking_embed_size > 0):
        long_late_chunking_embed_size = 0
        print(f'Long Late Chunking algorithm will be disabled because truncate max length is defined, hence documents are truncated.')
    
    assert (long_late_chunking_embed_size > 0 or truncate_max_length is not None), 'Define either long late chunking or truncation to handle documents.'

    model, has_instructions = load_model(model_name)

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)

    chunking_args = {
        'chunk_size': chunk_size,
        'n_sentences': n_sentences,
        'chunking_strategy': strategy,
        'model_has_instructions': has_instructions,
        'embedding_model_name': chunking_model if chunking_model else model_name,
    }

    if torch.cuda.is_available():
        model = model.cuda()

    model.eval()

    # Evaluate with late chunking
    tasks = [
        task_cls(
            chunked_pooling_enabled=True,
            tokenizer=tokenizer,
            prune_size=None,
            truncate_max_length=truncate_max_length,
            long_late_chunking_embed_size=long_late_chunking_embed_size,
            long_late_chunking_overlap_size=long_late_chunking_overlap_size,
            **chunking_args,
        )
    ]

    evaluation = MTEB(
        tasks=tasks,
        chunked_pooling_enabled=True,
        tokenizer=tokenizer,
        prune_size=None,
        **chunking_args,
    )
    evaluation.run(
        model,
        output_folder='results-chunked-pooling',
        eval_splits=[eval_split],
        overwrite_results=True,
        batch_size=BATCH_SIZE,
        encode_kwargs={'batch_size': BATCH_SIZE},
    )

    # Encode without late chunking
    tasks = [
        task_cls(
            chunked_pooling_enabled=False,
            tokenizer=tokenizer,
            prune_size=None,
            truncate_max_length=truncate_max_length,
            **chunking_args,
        )
    ]

    evaluation = MTEB(
        tasks=tasks,
        chunked_pooling_enabled=False,
        tokenizer=tokenizer,
        prune_size=None,
        **chunking_args,
    )
    evaluation.run(
        model,
        output_folder='results-normal-pooling',
        eval_splits=[eval_split],
        overwrite_results=True,
        batch_size=BATCH_SIZE,
        encode_kwargs={'batch_size': BATCH_SIZE},
    )


if __name__ == '__main__':
    main()
