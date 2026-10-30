"""Independent PDF upload input plus isolated existing project for execution checks."""

import argparse
import json
from pathlib import Path

import pymupdf
from prepare_interaction_fixture import prepare


def prepare_platform(directory):
    manifest = prepare(directory)
    path = Path(manifest['data_dir']) / 'user-upload.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72,72),'Independent research input')
        page.insert_text((72,110),'Synthetic acceptance document, not a scientific result.')
        page.insert_text((72,150),'Read the saved original and record the conditions and open questions.')
        pdf.new_page()  # Missing text is an intentional ingestion diagnostic.
        pdf.save(path)
    manifest['user_upload'] = str(path)
    (Path(manifest['data_dir'])/'browser-fixture.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,required=True)
    print(json.dumps(prepare_platform(parser.parse_args().output_dir),ensure_ascii=True))
