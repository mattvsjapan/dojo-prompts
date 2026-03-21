#!/usr/bin/env python3
"""Export a combined subs2srs TSV + media files into an Anki .apkg deck.

Usage:
    python3 apkg_export.py <tsv_path> <media_dir> <deck_name> <dest_dir>

Arguments:
    tsv_path   - Path to the combined TSV file (with header row)
    media_dir  - Directory containing audio and screenshot files
    deck_name  - Name for the Anki deck (also used for output filename)
    dest_dir   - Directory to write the .apkg file to
"""

import genanki
import csv
import os
import re
import sys
import hashlib

tsv_path = sys.argv[1]
media_dir = sys.argv[2]
deck_name = sys.argv[3]
dest_dir = sys.argv[4]

# Generate deterministic IDs from deck name so re-imports update existing cards
deck_id = int(hashlib.md5(deck_name.encode()).hexdigest()[:8], 16)
model_id = int(hashlib.md5((deck_name + '_model').encode()).hexdigest()[:8], 16)

model = genanki.Model(
    model_id,
    deck_name + ' Model',
    fields=[
        {'name': 'Audio'},
        {'name': 'Image'},
        {'name': 'Text'},
        {'name': 'Context'},
    ],
    templates=[{
        'name': 'Listening Card',
        'qfmt': '{{Audio}}',
        'afmt': '{{FrontSide}}<hr id=answer>{{Image}}<br>{{Text}}<br><br><small>{{Context}}</small>',
    }],
    css='.card { font-family: sans-serif; font-size: 24px; text-align: center; }',
)

deck = genanki.Deck(deck_id, deck_name)
media_files = []

with open(tsv_path, encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter='\t')
    for row in reader:
        # audioclip column contains e.g. [sound:filename.mp3]
        audioclip = row.get('audioclip', '')
        m = re.search(r'\[sound:(.+?)\]', audioclip)
        if not m:
            continue
        audio_filename = m.group(1)
        audio_path = os.path.join(media_dir, audio_filename)
        text = row.get('text', '')
        context = row.get('context', '')

        if not os.path.isfile(audio_path):
            continue

        # screenclip column contains HTML like <img src='name.jpg'>
        screenshot_html = row.get('screenclip', '')
        image_filename = ''
        image_field = ''
        if 'src=' in screenshot_html:
            image_filename = screenshot_html.split("src='")[1].split("'")[0]
            image_path = os.path.join(media_dir, image_filename)
            if os.path.isfile(image_path):
                image_field = '<img src="' + image_filename + '">'
                media_files.append(image_path)

        note = genanki.Note(
            model=model,
            fields=[
                '[sound:' + audio_filename + ']',
                image_field,
                text,
                context,
            ],
        )
        deck.add_note(note)
        media_files.append(audio_path)

output_path = os.path.join(dest_dir, deck_name + '.apkg')
package = genanki.Package(deck)
package.media_files = media_files
package.write_to_file(output_path)
print(f'Exported {len(media_files)} cards to {output_path}')
