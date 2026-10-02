"""Conservatively remove verified, superseded audiobook artifacts.

Original uploads, the requested HTML conversion, complete chapter audio, all
narration scripts, and active continuation utilities are always retained.
"""
from pathlib import Path
import json, subprocess
from datetime import datetime, timezone

HOME=Path('/home/user')
ROOT=HOME/'audiobook'
manifest_path=ROOT/'manifest.json'
m=json.loads(manifest_path.read_text())
protected={p.resolve() for p in (HOME/'uploads').rglob('*') if p.is_file()}
protected.add((HOME/'The Doctrine of Repentance - Thomas Watson.html').resolve())
protected.update(p.resolve() for p in (ROOT/'scripts').rglob('*') if p.is_file())
protected.update({manifest_path.resolve(),(ROOT/'Complete narration script.txt').resolve()})
retained_chapters={}

# Never delete a source installment until its entire spoken content is retained
# in valid, complete standalone chapter recordings.
for chapter in m['chapters']:
    if chapter['status']!='complete':
        continue
    audio=Path(chapter.get('complete_audio_file') or chapter.get('audio_file',''))
    assert audio.is_file(),f'Complete chapter master missing: {chapter["key"]}'
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(audio)]))
    assert float(info['format']['duration'])>1
    decoded=subprocess.run(['ffmpeg','-v','error','-i',str(audio),'-map','0:a:0','-f','null','-'],capture_output=True,text=True)
    assert decoded.returncode==0 and not decoded.stderr.strip(),decoded.stderr
    protected.add(audio.resolve())
    retained_chapters[chapter['key']]=str(audio)
    chapter['complete_audio_file']=str(audio)
    chapter['contains_entire_chapter']=True
    chapter['duration_seconds']=float(info['format']['duration'])
    for chunk in chapter['chunks']:
        chunk['canonical_audio']='chapter_audio_file'
        chunk['chapter_audio_file']=str(audio)

for chapter in m['chapters']:
    for chunk in chapter['chunks']:
        assert Path(chunk['script_file']).is_file()
        if chunk['status']!='complete':
            # Lossless compressed intermediates are smaller than raw WAVs.
            # assemble_batch.py decodes these into an excluded temporary cache.
            chunk['audio_file']=str(Path(chunk['audio_file']).with_suffix('.flac'))
            chunk['planned_audio_format']='flac'

candidates={}
def add(path,reason):
    path=Path(path)
    if not path.is_file():
        return
    resolved=path.resolve()
    assert resolved.is_relative_to(HOME),resolved
    if resolved in protected:
        return
    candidates[resolved]={'path':str(path),'bytes':path.stat().st_size,'reason':reason}

eligible_parts=[]
for part in m['parts']:
    if not all(key in retained_chapters for key in part['chapters']):
        continue
    eligible_parts.append(part)
    for field in ['audio_file','continuous_audio_file']:
        if part.get(field):
            add(part[field],'Superseded split recording; all narration retained in complete chapter masters')
    if part.get('transcript_file'):
        add(part['transcript_file'],'Duplicate installment transcript; full and segmented chapter scripts retained')
    add(ROOT/f'batch-{part["part"]:02}.json','Completed batch plan; progress and source ranges retained in manifest')
    add(ROOT/'scripts'/f'Batch {part["part"]:02} tool scripts.txt','Duplicate tool-input compilation; individual and complete scripts retained')

for name in ['cover.png','repentance.txt','html-reading-desktop.png','html-original-desktop.png','html-reading-mobile.png','ffmpeg-install.log','convert_pdf_to_html.py']:
    add(HOME/'work'/name,'Temporary conversion or preview/verification artifact')
for name in ['prepare_audiobook.py','assemble_part_01.py']:
    add(ROOT/name,'Obsolete one-time setup/assembly utility; active continuation utilities retained')
add(ROOT/'cover.jpg','Standalone extracted cover copy; source PDF and embedded cover images retained')

removed=[]
for item in candidates.values():
    path=Path(item['path'])
    assert path.resolve() not in protected
    path.unlink()
    removed.append(item)

for part in eligible_parts:
    part['status']='archived'
    part['superseded_by_complete_chapters']={key:retained_chapters[key] for key in part['chapters']}
    part['source_installments_removed_after_verified_assembly']=True
    part['transcript_compilation_removed']=True
for chapter in m['chapters']:
    if chapter['key'] in retained_chapters:
        for coverage in chapter.get('audio_coverage',[]):
            coverage['source_installment_removed_after_complete_assembly']=True

m['complete_chapter_files']=retained_chapters
m['canonical_audio']='Complete chapter MP3s are retained masters. Unfinished chapter sections remain available until their complete chapter is assembled.'
m['generation_policy']={
    'narrator_voice_id':m['voice_id'],
    'chapter_at_a_time':True,
    'maximum_speech_clips_per_turn':10,
    'intermediate_format':'Lossless FLAC; decoded WAV intermediates stay in excluded .cache directories',
    'final_format':'Single continuous MP3 per complete chapter',
    'label_partial_sections_explicitly':True,
    'never_treat_installment_number_as_chapter_number':True
}
report={
    'created_utc':datetime.now(timezone.utc).isoformat(),
    'removed_file_count':len(removed),'freed_bytes':sum(x['bytes'] for x in removed),
    'removed_files':removed,'retained_complete_chapters':retained_chapters,
    'next_position':m['next_position'],
    'retained_original_uploads':True,'retained_html_conversion':True,
    'retained_all_narration_scripts':True
}
m.setdefault('cleanup_history',[]).append({k:v for k,v in report.items() if k!='removed_files'})
manifest_path.write_text(json.dumps(m,indent=2,ensure_ascii=False),encoding='utf-8')
(ROOT/'Cleanup report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')

verification=ROOT/'chapters'/'03 - Complete chapter verification.json'
if verification.is_file():
    v=json.loads(verification.read_text())
    v['source_installments_removed_after_complete_assembly']=True
    v['retained_complete_chapter_audio']=retained_chapters['03']
    verification.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')

# Remove the known scratch folder only if it is empty; preserve unrelated files.
work=HOME/'work'
if work.is_dir() and not any(work.iterdir()):
    work.rmdir()

position=m.get('next_position')
next_line=(f'**Chapter {int(position["chapter_key"])}: {position["chapter_title"]}**, starting at segment {position["chunk_index"]}.' if position else 'All chapters and endnotes are complete.')
lines=['# The Doctrine of Repentance — audiobook progress','','**Author:** Thomas Watson  ','**Source:** Supplied Banner of Truth PDF  ',f'**Narrator:** Selected British English AI voice `{m["voice_id"]}`','','## Complete recordings','']
for chapter in m['chapters']:
    if chapter['key'] in retained_chapters:
        seconds=int(chapter['duration_seconds'])
        lines.append(f'- **{chapter["title"]}** — {seconds//60}:{seconds%60:02} — `{Path(retained_chapters[chapter["key"]]).name}`')
lines+=['','The complete Chapter 3 file includes all 26 segments, including its opening. Earlier split recordings have been removed because their audio is retained in these complete chapter files.','','## Next chapter','',next_line,'','## Continue safely','','Read `manifest.json` and reuse the registered `voice-00`. Generate up to ten pending scripts from the next unfinished chapter only; do not cross chapter boundaries. Use each script’s planned `.flac` audio path to keep intermediate files smaller without losing audio quality. The assembly utility automatically decodes compressed inputs to temporary WAVs in an excluded cache directory, then creates a continuous MP3.','','Choose the next internal batch number using `max(part["part"] for part in manifest["parts"]) + 1`; archived parts keep their history but their files are intentionally absent. Write the selected pending records to `batch-NN.json`, then run `assemble_batch.py NN` after speech generation. Clearly label any output as a partial chapter until all segments are done. When the chapter is finished, run `assemble_complete_chapter.py CHAPTER_KEY` to create its complete recording. `cleanup_workspace.py` can then remove superseded source installments only after confirming complete chapter masters are present and decode correctly.','','Original uploads, the requested HTML file, all complete/segmented narration scripts, and the active continuation utilities were retained. Preparation is already complete; do not reinitialize the progress manifest.']
(ROOT/'Audiobook progress.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

# Final checks: all preserved content and the next starting point remain.
for path in protected:
    assert path.is_file(),path
if position:
    next_chapter=next(c for c in m['chapters'] if c['key']==position['chapter_key'])
    next_chunk=next(x for x in next_chapter['chunks'] if x['index']==position['chunk_index'])
    assert next_chunk['status']!='complete' and Path(next_chunk['script_file']).is_file()
print(json.dumps({
    'deleted_files':len(removed),'freed_bytes':report['freed_bytes'],
    'freed_MiB':round(report['freed_bytes']/1024/1024,2),
    'kept_complete_chapters':list(retained_chapters),
    'next_chapter':(str(int(position['chapter_key']))+' — '+position['chapter_title']) if position else 'Book complete',
    'narrator_retained':m['voice_id'],'original_uploads_and_html_preserved':True
},indent=2,ensure_ascii=False))
