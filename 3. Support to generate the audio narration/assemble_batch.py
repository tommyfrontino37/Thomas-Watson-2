"""Assemble one pending narration batch without reinitializing book progress.

Complete chapter recordings are the retained masters. In-progress sections
are kept until their chapter is assembled. Lossless FLAC clips save workspace
space; decoded temporary WAV files stay in the excluded cache directory.
Usage: python assemble_batch.py 2
"""
from pathlib import Path
import sys, json, subprocess, wave, re, shutil
from collections import OrderedDict

ROOT=Path('/home/user/audiobook')
part_number=int(sys.argv[1])
manifest_path=ROOT/'manifest.json'
manifest=json.loads(manifest_path.read_text())
assert not any(p['part']==part_number for p in manifest['parts']), 'This installment already exists.'
batch=json.loads((ROOT/f'batch-{part_number:02}.json').read_text())
assert 0<len(batch)<=10
chapter_map={c['key']:c for c in manifest['chapters']}
WORK=ROOT/'.cache'/f'batch-{part_number:02}'
WORK.mkdir(parents=True,exist_ok=True)

params=None
pcm_parts=[]
chapter_groups=OrderedDict()
chunk_times=[]
position=0
for index,selected in enumerate(batch):
    chapter=chapter_map[selected['chapter_key']]
    chunk=next(c for c in chapter['chunks'] if c['name']==selected['name'])
    assert chunk['status']!='complete', 'Do not regenerate completed narration.'
    source=Path(selected['audio_file'])
    decoded=source
    if source.suffix.lower()!='.wav':
        decoded=WORK/f'{selected["name"]}-decoded.wav'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(source),'-map','0:a:0','-ac','1','-ar','44100','-c:a','pcm_s16le',str(decoded)],check=True)
    with wave.open(str(decoded),'rb') as audio:
        these_params=(audio.getnchannels(),audio.getsampwidth(),audio.getframerate())
        if params is None:
            params=these_params
        assert these_params==params and params[0]==1 and params[1]==2
        pcm=audio.readframes(audio.getnframes())
        assert len(pcm)>44100
    channels,width,rate=params
    bytes_per_second=channels*width*rate
    if index:
        chapter_changed=selected['chapter_key']!=batch[index-1]['chapter_key']
        pause=1.8 if chapter_changed else .16
        silence=b'\x00'*(round(pause*rate)*channels*width)
        pcm_parts.append(silence)
        position+=len(silence)
    start=position/bytes_per_second
    pcm_parts.append(pcm)
    position+=len(pcm)
    end=position/bytes_per_second
    key=selected['chapter_key']
    if key not in chapter_groups:
        chapter_groups[key]={'key':key,'title':chapter['title'],'start':start,'end':end,'first_chunk':chunk['index'],'last_chunk':chunk['index'],'pcm':[]}
    else:
        chapter_groups[key]['pcm'].append(b'\x00'*(round(.16*rate)*channels*width))
    chapter_groups[key]['pcm'].append(pcm)
    chapter_groups[key]['last_chunk']=chunk['index']
    chapter_groups[key]['end']=end
    chunk_times.append({'name':chunk['name'],'chapter_key':key,'index':chunk['index'],'start_seconds':start,'end_seconds':end})

full_pcm=b''.join(pcm_parts)
full_duration=len(full_pcm)/bytes_per_second

def write_wave(path,pcm):
    with wave.open(str(path),'wb') as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(width)
        audio.setframerate(rate)
        audio.writeframes(pcm)

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-show_chapters','-of','json',str(path)]))

def encode(wav_path,audio_path,title,chapter_metadata=None):
    # Use a single audio-only track, without attached cover art or ID3 chapter
    # markers. This avoids players displaying a chapter duration as the file
    # duration. Exact chapter/segment timings remain in manifest.json.
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(wav_path),
         '-map','0:a:0','-c:a','libmp3lame','-b:a','64k','-ar','22050','-ac','1',
         '-map_metadata','-1','-map_chapters','-1','-write_xing','1','-id3v2_version','3']
    cmd+=['-metadata','title='+title,'-metadata','album=The Doctrine of Repentance','-metadata','artist=AI narration','-metadata','album_artist=Thomas Watson','-metadata','composer=Thomas Watson','-metadata','genre=Audiobook','-metadata','comment=AI-narrated from the Banner of Truth PDF supplied by the listener; selected narrator voice.']
    cmd.append(str(audio_path))
    subprocess.run(cmd,check=True)
    subprocess.run(['ffmpeg','-v','error','-i',str(audio_path),'-map','0:a','-f','null','-'],check=True)
    return probe(audio_path)

# Name partial recordings by chapter and section, not by an installment
# number that could be mistaken for a chapter number.
if len(chapter_groups)==1:
    first_group=next(iter(chapter_groups.values()))
    chapter_key=first_group['key']
    section_number=1+sum(any(g.get('chapter_key')==chapter_key for g in p.get('chapter_ranges',[])) for p in manifest['parts'])
    safe_title=re.sub(r'[<>:"/\\|?*]','-',first_group['title'])
    part_path=ROOT/'sections'/f'{chapter_key} - {safe_title} - Section {section_number:02}.mp3'
    display_title=f'Chapter {int(chapter_key)} — {first_group["title"]} — Section {section_number}'
else:
    part_path=ROOT/'sections'/f'The Doctrine of Repentance - Part {part_number:02}.mp3'
    display_title=f'Part {part_number:02} — The Doctrine of Repentance'
part_path.parent.mkdir(parents=True,exist_ok=True)
for group in chapter_groups.values():
    chapter=chapter_map[group['key']]
    all_in_batch=(group['first_chunk']==1 and group['last_chunk']==len(chapter['chunks']))
    if all_in_batch:
        group['label']='Chapter '+str(int(group['key']))+': '+group['title']
    elif group['first_chunk']==1:
        group['label']='Chapter '+str(int(group['key']))+': '+group['title']+' — opening portion'
    else:
        group['label']='Chapter '+str(int(group['key']))+': '+group['title']+' — continued'

meta=WORK/f'part-{part_number:02}.ffmetadata'
meta_lines=[';FFMETADATA1','album=The Doctrine of Repentance','artist=AI narration','composer=Thomas Watson']
groups=list(chapter_groups.values())
for i,group in enumerate(groups):
    end=groups[i+1]['start'] if i+1<len(groups) else full_duration
    label=group['label'].replace('\\','\\\\').replace('=','\\=').replace(';','\\;').replace('#','\\#')
    meta_lines+=['[CHAPTER]','TIMEBASE=1/1000',f'START={round(group["start"]*1000)}',f'END={round(end*1000)}','title='+label]
meta.write_text('\n'.join(meta_lines)+'\n',encoding='utf-8')
part_wav=WORK/f'part-{part_number:02}.wav'
write_wave(part_wav,full_pcm)
info=encode(part_wav,part_path,display_title,meta)
actual_duration=float(info['format']['duration'])
assert abs(actual_duration-full_duration)<.25
assert not info.get('chapters')
assert len(info['streams'])==1 and info['streams'][0]['codec_type']=='audio'

# Optional individual tracks for chapters wholly contained in this installment.
# Multi-installment chapters remain in the canonical Part files to avoid storing
# another full duplicate of a long audiobook in the limited workspace.
new_chapter_audio=[]
for group in groups:
    chapter=chapter_map[group['key']]
    if group['first_chunk']==1 and group['last_chunk']==len(chapter['chunks']):
        if len(groups)==1:
            # Reuse this verified section as the complete chapter's source;
            # do not encode an unnecessary duplicate standalone track.
            chapter['audio_file']=str(part_path)
            chapter['duration_seconds']=actual_duration
            new_chapter_audio.append(str(part_path))
            continue
        chapter_pcm=b''.join(group['pcm'])
        chapter_wav=WORK/f'chapter-{group["key"]}.wav'
        write_wave(chapter_wav,chapter_pcm)
        filename=re.sub(r'[<>:"/\\|?*]','-',chapter['title'])
        chapter_audio=ROOT/'chapters'/f'{group["key"]} - {filename}.mp3'
        chapter_info=encode(chapter_wav,chapter_audio,group['title'])
        chapter['audio_file']=str(chapter_audio)
        chapter['duration_seconds']=float(chapter_info['format']['duration'])
        new_chapter_audio.append(str(chapter_audio))

for timing in chunk_times:
    chapter=chapter_map[timing['chapter_key']]
    chunk=next(c for c in chapter['chunks'] if c['name']==timing['name'])
    chunk['status']='complete'
    chunk['part_number']=part_number
    chunk['part_audio_file']=str(part_path)
    chunk['part_start_seconds']=timing['start_seconds']
    chunk['part_end_seconds']=timing['end_seconds']
    chunk['duration_seconds']=timing['end_seconds']-timing['start_seconds']
    chunk['source_audio_removed_after_assembly']=True
    chunk['canonical_audio']='part_audio_file'
for chapter in manifest['chapters']:
    completed=sum(c['status']=='complete' for c in chapter['chunks'])
    chapter['status']='complete' if completed==len(chapter['chunks']) else 'partial' if completed else 'pending'
    chapter['completed_chunks']=completed

transcript=ROOT/f'Part {part_number:02} - Narration transcript.txt'
transcript.write_text('\n\n'.join(Path(c['script_file']).read_text() for c in batch),encoding='utf-8')
part_record={
 'part':part_number,'audio_file':str(part_path),'chapters':[g['key'] for g in groups],
 'duration_seconds':actual_duration,'transcript_file':str(transcript),'status':'complete',
 'continuous_audio_file':str(part_path),'embedded_chapter_markers':False,'playback_format':'Continuous audio-only MP3',
 'chapter_ranges':[{'chapter_key':g['key'],'title':g['title'],'start_seconds':g['start'],'end_seconds':g['end'],'first_chunk':g['first_chunk'],'last_chunk':g['last_chunk'],'chapter_complete':chapter_map[g['key']]['status']=='complete'} for g in groups],
 'chunk_ranges':chunk_times
}
manifest['parts'].append(part_record)
manifest['canonical_audio']='Complete chapter MP3s are retained masters. Unfinished chapter sections remain available until the complete chapter is assembled.'
next_position=next(({'chapter_key':c['key'],'chapter_title':c['title'],'chunk_index':x['index'],'script_file':x['script_file']} for c in manifest['chapters'] for x in c['chunks'] if x['status']!='complete'),None)
manifest['next_position']=next_position
manifest['next_chapter']=next_position['chapter_key'] if next_position else None
manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')

def mmss(seconds):
    seconds=round(seconds)
    return f'{seconds//60}:{seconds%60:02}'

readme=['# The Doctrine of Repentance — audiobook in progress','','**Author:** Thomas Watson  ','**Edition:** Banner of Truth PDF supplied by the listener  ','**Narrator:** AI narration, selected British English voice (`voice-00`)','','## Available installments','']
for part in manifest['parts']:
    if part.get('status')=='archived' or not Path(part['audio_file']).is_file():
        continue
    titles=[chapter_map[key]['title'] for key in part['chapters']]
    readme.append(f'- **Part {part["part"]:02}** — {mmss(part["duration_seconds"])} — '+ '; '.join(titles))
readme+=['','These are installments of the audiobook, not a claim that the whole book is finished. Starting with Part 03, each installment is a continuous audio-only MP3 without embedded chapter markers or artwork, to avoid player/preview duration confusion. Chapter and segment timing ranges remain in manifest.json.']
completed_titles=[c['title'] for c in manifest['chapters'] if c['status']=='complete']
readme+=['','**Completed sections:** '+ '; '.join(completed_titles)+'.']
for chapter in manifest['chapters']:
    if chapter['status']=='partial':
        readme+=['',f'**In progress:** {chapter["title"]} — {chapter["completed_chunks"]} of {len(chapter["chunks"])} narration segments complete.']
if next_position:
    readme+=['',f'**Resume at:** Chapter {int(next_position["chapter_key"])} — {next_position["chapter_title"]}, segment {next_position["chunk_index"]}.']
readme+=['','## Text preparation','','The scripts are readings of the supplied edition, not summaries. PDF line wrapping and discretionary hyphens are removed, Bible reference abbreviations are expanded for speech, and running footnote numbers are omitted. The endnotes are scheduled for a separate final track. Ebook licensing, navigation and publisher contact pages are not narrated; original notices remain in the PDF and converted HTML. This is AI narration, not a commercially published Banner of Truth audiobook.','','## Continue safely','','Read `manifest.json` for authoritative progress. Reuse the registered narrator `voice-00`. Select up to ten pending scripts from the next unfinished chapter, in order, and synthesize each using its planned FLAC audio path. Then run `assemble_batch.py PART_NUMBER`. Preparation is already finished; do not reinitialize the manifest. Completed source clips are removed after verification. Complete chapter MP3s are the retained listening masters; partial chapter recordings remain until their chapter is complete.']
(ROOT/'Audiobook progress.md').write_text('\n'.join(readme)+'\n',encoding='utf-8')

# Remove only verified, generated intermediate WAVs, never prior deliverables.
for selected in batch:
    Path(selected['audio_file']).unlink(missing_ok=True)
shutil.rmtree(WORK)
print(json.dumps({
 'part':part_number,'main_audio':str(part_path),'duration':mmss(actual_duration),
 'duration_seconds':actual_duration,'size_bytes':part_path.stat().st_size,
 'sections':[{'title':g['label'],'start':mmss(g['start']),'first_chunk':g['first_chunk'],'last_chunk':g['last_chunk']} for g in groups],
 'individual_complete_chapters':new_chapter_audio,'next_position':next_position,
 'audio_decoding':'verified','chapter_markers':len(info.get('chapters',[]))
},indent=2,ensure_ascii=False))
