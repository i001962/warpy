# Warpy (Beta)

[Farcaster](https://github.com/farcasterxyz/protocol) is an Ethereum-based programmable social network. Warpy provides open-source Farcaster datasets.

To see what you can do with the datasets, see [example.ipynb](example.ipynb). To see the data schema, see [models.py](models.py).

One-command install on MacOS and Linux machines: run `make install`. Windows machines: it's recommended to use [WSL](https://docs.microsoft.com/en-us/windows/wsl/install-win10) and run `make install` there. If you don't want to use `make`, you can run `pip install -r requirements.txt` manually inside a virtual environment.

All of `main.py` commands:

```
Usage: main.py [OPTIONS] COMMAND [ARGS]...

Options:
  --help    Show this message and exit.

Commands:
  download  Download datasets.
  env
  indexer
  package   Package and zip datasets.
  query
  upload    Upload datasets.
```

Some example commands:

```bash
# Download the latest dataset
python main.py download

# Index the latest casts
python main.py indexer cast

# Set OpenAI environment variables
python main.py env openai

# Ways to query the database
python main.py query "get latest cast by dwr"
python main.py query --raw "select count(*) from users"
python main.py query --raw "yoursql.sql"
python main.py query "get users followers is more than 5k" --csv
```

Dataset latest cast timestamp: 1681623420000; dataset highest fid: 12151; dataset highest block number: 17071892; tar.gz shasum: `38319a9770743f01a9bed79179f343bfd4879660d51dedfda026247510494a31`.
