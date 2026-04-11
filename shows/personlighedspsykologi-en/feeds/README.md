The RSS feed for Personlighedspsykologi will be written here by the automation.

- Local runs of `gdrive_podcast_feed.py` will overwrite `rss.xml` in this directory.
- Commit the generated `rss.xml` when you are ready to publish the show.
- This show intentionally adds synthetic `[Lydbog]` tail items for configured Grundbog chapters. Those items reuse real Drive enclosure URLs but use GUIDs with `#tail-grundbog-*` suffixes, so a strict GUID-vs-Drive-ID comparison will show them as feed-only entries.
