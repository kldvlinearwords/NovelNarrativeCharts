#!/usr/bin/env python
"""
Generates novel narrative charts.

Based on https://github.com/niskander/ComicBookNarrativeCharts.

Example usage for one book:

  ./novel_narrative_charts.py \
      --book \
      --filename=book_text.txt \
      --title="Book Title" \
      --character_group=Alice,Bob,Charlie \
      --character_group=Xavier,Yvette,Zod

Characters listed in a character group will all have the same dispaly color on
the charts. If a character has multiple aliases, separate them with pipes:

      --character_group=Clark Kent\|Superman

To render more than one book at a time, simply relist all the argmuents in
series, separated by a new `--book` argument:

  ./novel_narrative_charts.py \
      --book \
      --filename=book_text1.txt \
      --title="Book Title" \
      --character_group=Alice,Bob,Charlie \
      --character_group=Xavier,Yvette,Zod \
      --book \
      --filename=book_text2.txt \
      --title="Book Title II: Electric Boogaloo" \
      --character_group=Alice,Bob,Charlie \
      --character_group=Xavier,Yvette,Zod
"""

import jinja2
import json
import re
import sys


# TODO: Make the chapter regex something that can be specified via argument.
CHAPTER_REGEX = r'\s*(Epilogue|Prelude|Prologue|Interlude|Chapter\s+\d+).*'


class Character(object):
  """A character being tracked in a story."""
  _ID = 0

  def __init__(self, group, aliases):
    self.group = group
    # self.name = name
    self.aliases = aliases
    self.id = Character._ID
    Character._ID += 1

  @property
  def name(self):
    return self.aliases[0]

  def to_json(self):
    return {
      'group': self.group,
      'id': self.id,
      'name': self.name,
    }


class Book(object):
  """A book as a collection of chapters referencing characters."""

  def __init__(self, title=None, lines=None, characters=None, gini_coeff=1.0):
    self.title = title
    self.lines = lines
    self.gini_coeff = gini_coeff
    self.chapters = Chapter.ParseChapters(lines)
    self.characters = characters
    self._FindCharacters()
    self.scenes = []
    self._BuildScenes()

  def WordCount(self):
    return sum(len(line.split()) for line in self.lines)

  def _FindCharacters(self):
    for chapter in self.chapters:
      chapter.FindCharacters(self.characters)

  def _BuildScenes(self):
    num_panels = 500.0
    num_even_panels = (1.0 - self.gini_coeff) * num_panels
    num_word_count_panels = self.gini_coeff * num_panels
    panels_per_chapter = num_even_panels / float(len(self.chapters))
    panels_per_word_count = num_word_count_panels / float(self.WordCount())
    narrative = {
        'panels': int(num_panels),
    }
    # Apportion chapters over the synthetic panel count using their word counts.
    cum_panel_count = 0.0
    for ix, chapter in enumerate(self.chapters):
      panel_count = (panels_per_chapter +
                     panels_per_word_count * chapter.WordCount())
      sorted_chars = sorted([
          (ch.id, ch.name) for ch in chapter.GetCharacters()])
      self.scenes.append({
          'title': chapter.title,
          'duration': int(panel_count),
          'start': int(cum_panel_count),
          'chars': [s[0] for s in sorted_chars],
          'named_chars': [s[1] for s in sorted_chars],
          'id': ix,
      })
      cum_panel_count += panel_count

  def to_json(self):
    return {
      'title': self.title,
      'characters': [_.to_json() for _ in self.characters],
      'scenes': self.scenes,
    }


class Chapter(object):
  """A chapter having lines and referencing characters."""

  def __init__(self, title=None, lines=None):
    self.title = title
    self.lines = lines
    self._word_count = None
    self._character_occs = {}

  @staticmethod
  def ParseChapters(lines):
    separator = ''
    chapters = []
    last_line_ix = 0
    last_chapter_match = None
    next_chapter_match = None
    def get_chapter(chapter_match, last_line_end):
      # Creates a chapter from `lines[last_line_ix:last_line_end]`.
      return Chapter(
          title=chapter_match.group(0),
          lines=lines[last_line_ix:last_line_end])

    for i in range(len(lines)):
      line = lines[i]
      next_chapter_match = re.match(CHAPTER_REGEX, line)
      if next_chapter_match:
        print('Matched chapter:', next_chapter_match.group(0))
        # Save the last chapter with all its lines.
        if last_chapter_match:
          chapters.append(get_chapter(last_chapter_match, i))

        last_chapter_match = next_chapter_match
        last_line_ix = i + 1

    if len(lines) > last_line_ix:
      chapters.append(get_chapter(last_chapter_match, len(lines)))

    return chapters

  def WordCount(self):
    if self._word_count is None:
      self._word_count = sum(len(line.split()) for line in self.lines)

    return self._word_count

  def FindCharacters(self, characters):
    for line in self.lines:
      for character in characters:
        for alias in character.aliases:
          if alias in line:
            self.AddCharacter(character)

  def AddCharacter(self, character):
    if character.name not in self._character_occs:
      self._character_occs[character.name] = {
          'character': character,
          'count': 1,
      }
    else:
      self._character_occs[character.name]['count'] += 1

  def GetCharacters(self):
    return [_['character'] for _ in self._character_occs.values()]

  def ToJson(self):
    return {
        'title': self.title,
        'num_lines': len(self.lines),
        'word_count': self.WordCount(),
        'characters': dict((k, v['count']) for (k, v) in self._character_occs.iteritems()),
    }


BOOK_ARG = '--book'
CHARACTER_GROUP_ARG = '--character_group='
FILENAME_ARG = '--filename='
TEMPLATE_FILE = 'novel_narrative_charts.html'
TITLE_ARG = '--title='

# TODO: Make this an argument.
gini_coeff = 1.0
# Split each book's arguments out for separate processing.
book_ixes = [i for i in range(1, len(sys.argv)) if sys.argv[i] == BOOK_ARG] + [len(sys.argv)]
book_args = [sys.argv[book_ixes[i] + 1 : book_ixes[i + 1]] for i in range(len(book_ixes) - 1)]

books = []
for book_arg in book_args:
  filename = None
  title = None
  characters = []
  group_id = 0
  for arg in book_arg:
    if arg.startswith(CHARACTER_GROUP_ARG):
      body = arg[len(CHARACTER_GROUP_ARG):]
      group_characters = [_.split('|') for _ in body.split(',')]
      group_name = group_characters[0][0]
      for character in group_characters:
        characters.append(Character(group_id, character))

      group_id += 1
    elif arg.startswith(TITLE_ARG):
      title = arg[len(TITLE_ARG):]
    elif arg.startswith(FILENAME_ARG):
      filename = arg[len(FILENAME_ARG):]

  books.append(
      Book(
          title=title,
          characters=characters,
          lines=open(filename, 'r').readlines(),
          gini_coeff=gini_coeff))

# Render the web page with all books at once.
template_loader = jinja2.FileSystemLoader(searchpath='./')
template_env = jinja2.Environment(loader=template_loader)
template = template_env.get_template(TEMPLATE_FILE)
with open('novel_narrative_charts_output.html', 'w') as f:
  f.write(template.render(books=[_.to_json() for _ in books]))
