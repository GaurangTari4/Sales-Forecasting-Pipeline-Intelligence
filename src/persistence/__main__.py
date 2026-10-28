import argparse
from pathlib import Path
from src.validation.io import load_csv_dataset
from .database import Database,ingest_generated_dataset
if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('command',choices=('migrate','seed')); p.add_argument('--input',type=Path,default=Path('output/starter')); a=p.parse_args(); db=Database(); db.migrate(); print(ingest_generated_dataset(db,load_csv_dataset(a.input)) if a.command=='seed' else 'migrations applied')
