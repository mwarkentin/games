# Music

MIDI files the games play on chip voices of their own (see the Music section
of `war.html`). They hold notes, not recordings: a few KB each, played live
in the page, so they work offline like everything else.

Every piece here is in the public domain twice over: the composer died long
ago, and the edition it came from was placed in the public domain by its
typesetter. They come from the [Mutopia Project](https://www.mutopiaproject.org)'s
LilyPond sources, all at commit
[`2144afd`](https://github.com/MutopiaProject/MutopiaProject/tree/2144afd6f52d56c5b6995b8b589ef1268b3139f0/ftp),
compiled to MIDI with LilyPond 2.25.12.

| File | Piece | Mutopia source | Licence |
| --- | --- | --- | --- |
| `hall-of-the-mountain-king.mid` | Edvard Grieg, *In the Hall of the Mountain King*, Peer Gynt Suite No. 1, Op. 46 No. 4 (1874) | [1888](https://github.com/MutopiaProject/MutopiaProject/blob/2144afd6f52d56c5b6995b8b589ef1268b3139f0/ftp/GriegE/O46/Dans_l_antre_du_roi_de_la_montagne/Dans_l_antre_du_roi_de_la_montagne.ly) | Public Domain |
| `prelude-in-c-minor.mid` | Frédéric Chopin, Prelude in C minor, Op. 28 No. 20 | [472](https://github.com/MutopiaProject/MutopiaProject/blob/2144afd6f52d56c5b6995b8b589ef1268b3139f0/ftp/ChopinFF/O28/Chop-28-20/Chop-28-20.ly) | Public Domain |
| `stars-and-stripes-forever.mid` | John Philip Sousa, *The Stars and Stripes Forever* (1896) | [626](https://github.com/MutopiaProject/MutopiaProject/blob/2144afd6f52d56c5b6995b8b589ef1268b3139f0/ftp/SousaJP/TheStarsAndStripesForever/TheStarsAndStripesForever.ly) | Public Domain |
| `the-entertainer.mid` | Scott Joplin, *The Entertainer* (1902) | [263](https://github.com/MutopiaProject/MutopiaProject/blob/2144afd6f52d56c5b6995b8b589ef1268b3139f0/ftp/JoplinS/entertainer/entertainer.ly) | Public Domain |
| `thunder-and-lightning.mid` | Johann Strauss II, *Thunder and Lightning* polka, Op. 324 | [610](https://github.com/MutopiaProject/MutopiaProject/blob/2144afd6f52d56c5b6995b8b589ef1268b3139f0/ftp/StraussJJ/O324/blitz/blitz.ly) | Public Domain |

## Adding a piece

1. Find a piece with `copyright` or `license` set to Public Domain (or
   CC0) in its `.ly` file's header. Other Creative Commons licences need
   the arranger credited here and in the game, so prefer those that don't.
   Mutopia's own MIDI files aren't in its repository, so compile the source:

   ```sh
   # LilyPond from PyPI; this prints where it is, with convert-ly beside it
   uv tool run --from lilypond python -c "import lilypond; print(lilypond.executable())"
   convert-ly -e piece.ly               # bring old syntax up to date
   lilypond -dno-print-pages piece.ly   # writes piece.midi
   ```

   LilyPond runs any Scheme code a `.ly` file holds, and no longer has a
   safe mode, so read the file first.
2. Save it here as `<name>.mid`, add a row above, and use it in a game.
   Piano music works best: the right hand becomes the tune and the left
   hand the bass.
