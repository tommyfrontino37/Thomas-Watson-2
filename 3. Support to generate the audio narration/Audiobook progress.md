# The Doctrine of Repentance — audiobook progress

**Author:** Thomas Watson  
**Source:** Supplied Banner of Truth PDF  
**Narrator:** Selected British English AI voice `voice-00`

## Complete recordings

- **Epistle to the Reader** — 4:28 — `00 - Epistle to the Reader.mp3`
- **A Preliminary Discourse** — 8:06 — `01 - A Preliminary Discourse.mp3`
- **Counterfeit Repentance** — 4:17 — `02 - Counterfeit Repentance.mp3`
- **The Nature of True Repentance (1)** — 41:02 — `03 - The Nature of True Repentance (1) - Complete.mp3`
- **The Nature of True Repentance (2)** — 42:11 — `04 - The Nature of True Repentance (2) - Complete.mp3`
- **The Reasons Enforcing Repentance with a Warning to the Impenitent** — 7:46 — `05 - The Reasons Enforcing Repentance with a Warning to the Impenitent - Complete.mp3`

The complete Chapter 3 file includes all 26 segments, including its opening. Earlier split recordings have been removed because their audio is retained in these complete chapter files.

## Next chapter

**Chapter 6: Powerful Motives to Repentance**, starting at segment 1.

## Continue safely

Read `manifest.json` and reuse the registered `voice-00`. Generate up to ten pending scripts from the next unfinished chapter only; do not cross chapter boundaries. Use each script’s planned `.flac` audio path to keep intermediate files smaller without losing audio quality. The assembly utility automatically decodes compressed inputs to temporary WAVs in an excluded cache directory, then creates a continuous MP3.

Choose the next internal batch number using `max(part["part"] for part in manifest["parts"]) + 1`; archived parts keep their history but their files are intentionally absent. Write the selected pending records to `batch-NN.json`, then run `assemble_batch.py NN` after speech generation. Clearly label any output as a partial chapter until all segments are done. When the chapter is finished, run `assemble_complete_chapter.py CHAPTER_KEY` to create its complete recording. `cleanup_workspace.py` can then remove superseded source installments only after confirming complete chapter masters are present and decode correctly.

Original uploads, the requested HTML file, all complete/segmented narration scripts, and the active continuation utilities were retained. Preparation is already complete; do not reinitialize the progress manifest.

