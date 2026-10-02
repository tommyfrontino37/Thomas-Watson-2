"""Create a complete chapter from its verified installment ranges.

Usage: python assemble_complete_chapter.py 03
Audio packets are copied rather than re-synthesized or re-encoded. Completed
installments are retained. Small seek margins fall only within chapter-break
silence so the chapter's first and last words are not clipped.
"""
from pathlib import Path
import sys, json, subprocess, tempfile, re

ROOT=Path('/home/user/audiobook')
key=sys.argv[1].zfill(2)
manifest_path=ROOT/'manifest.json'
m=json.loads(manifest_path.read_text())
chapter=next(c for c in m['chapters'] if c['key']==key)
assert chapter['status']=='complete'
assert all(x['status']=='complete' for x in chapter['chunks'])

# A completed chapter is the retained master after superseded installments
# are removed. Do not require deleted source parts to reopen that master.
existing=chapter.get('complete_audio_file') or chapter.get('audio_file')
if existing and Path(existing).is_file() and chapter.get('contains_entire_chapter'):
    print(json.dumps({'file':existing,'already_complete':True,'duration_seconds':chapter.get('duration_seconds')},indent=2))
    raise SystemExit(0)

full_script=(ROOT/'scripts'/f'{key} - {chapter["title"]}.txt').read_text()
joined=''.join(Path(x['script_file']).read_text() for x in chapter['chunks'])
assert re.sub(r'\s+','',full_script)==re.sub(r'\s+','',joined)

source_ranges=[]
for part in sorted(m['parts'],key=lambda p:p['part']):
    for group in part.get('chapter_ranges',[]):
        if group['chapter_key']==key:
            audio=Path(part.get('continuous_audio_file') or part['audio_file'])
            assert audio.is_file(),audio
            source_ranges.append({'part_number':part['part'],'audio_file':str(audio),**group})
indices=[i for group in source_ranges for i in range(group['first_chunk'],group['last_chunk']+1)]
assert indices==list(range(1,len(chapter['chunks'])+1)), 'Missing, duplicated, or misordered chapter segments'
assert indices[0]==1

filename=re.sub(r'[<>:"/\\|?*]','-',chapter['title'])
output=ROOT/'chapters'/f'{key} - {filename} - Complete.mp3'
output.parent.mkdir(exist_ok=True)


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-show_chapters','-of','json',str(path)]))

cache=Path('/home/user/.cache')
cache.mkdir(exist_ok=True)
coverage=[]
with tempfile.TemporaryDirectory(prefix='complete-chapter-',dir=cache) as temp:
    temp=Path(temp)
    pieces=[]
    for index,group in enumerate(source_ranges):
        source=Path(group['audio_file'])
        info=probe(source)
        duration=float(info['format']['duration'])
        stream=next(s for s in info['streams'] if s['codec_type']=='audio')
        assert stream['codec_name']=='mp3' and stream['sample_rate']=='22050' and stream['channels']==1
        # Leave at most 0.32 s of the silent chapter break before an opening.
        start=max(0,group['start_seconds']-.32)
        end=duration if duration-group['end_seconds']<.25 else min(duration,group['end_seconds']+.16)
        if start==0 and end==duration:
            piece=source
        else:
            piece=temp/f'{index:02}.mp3'
            cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(source),'-ss',f'{start:.9f}']
            if end<duration:
                cmd+=['-t',f'{end-start:.9f}']
            cmd+=['-map','0:a:0','-c:a','copy','-map_metadata','-1','-map_chapters','-1','-write_xing','1',str(piece)]
            subprocess.run(cmd,check=True)
        piece_info=probe(piece)
        piece_duration=float(piece_info['format']['duration'])
        assert abs(piece_duration-(end-start))<.3
        pieces.append(piece)
        coverage.append({
            'source_part':group['part_number'],
            'source_file':str(source),
            'first_script':f'{key}-{group["first_chunk"]:02}',
            'last_script':f'{key}-{group["last_chunk"]:02}',
            'first_chunk':group['first_chunk'],'last_chunk':group['last_chunk'],
            'source_start_seconds':start,'source_end_seconds':end,
            'audio_duration_seconds':piece_duration
        })
    concat=temp/'concat.txt'
    concat.write_text(''.join("file '"+str(p).replace("'","'\\''")+"'\n" for p in pieces),encoding='utf-8')
    subprocess.run([
        'ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),
        '-map','0:a:0','-c:a','copy','-map_metadata','-1','-map_chapters','-1','-write_xing','1','-id3v2_version','3',
        '-metadata',f'title=Chapter {int(key)} - {chapter["title"]} (Complete)',
        '-metadata','album=The Doctrine of Repentance','-metadata','artist=AI narration',
        '-metadata','composer=Thomas Watson','-metadata','genre=Audiobook',
        '-metadata',f'comment=Complete Chapter {int(key)}; all narration segments {key}-01 through {key}-{len(chapter["chunks"]):02} in book order.',
        str(output)
    ],check=True)

# Decode every audio packet and check the complete file, not only its header.
check=subprocess.run(['ffmpeg','-v','error','-i',str(output),'-map','0:a:0','-f','null','-'],capture_output=True,text=True)
assert check.returncode==0 and not check.stderr.strip(),check.stderr
final_info=probe(output)
assert len(final_info['streams'])==1 and final_info['streams'][0]['codec_type']=='audio'
assert not final_info.get('chapters')
final_duration=float(final_info['format']['duration'])
assert abs(final_duration-sum(x['audio_duration_seconds'] for x in coverage))<1

chapter['audio_file']=str(output)
chapter['complete_audio_file']=str(output)
chapter['duration_seconds']=final_duration
chapter['contains_entire_chapter']=True
chapter['verified_audio_script_order']=[f'{key}-{i:02}' for i in indices]
chapter['audio_coverage']=coverage
chapter['playback_format']='Single continuous audio-only MP3, complete chapter'
m.setdefault('complete_chapter_files',{})[key]=str(output)
manifest_path.write_text(json.dumps(m,indent=2,ensure_ascii=False),encoding='utf-8')

# Keep a concise audit alongside the full recording for continuation/verification.
audit={
    'chapter':int(key),'title':chapter['title'],'audio_file':str(output),
    'duration_seconds':final_duration,'script_segments':chapter['verified_audio_script_order'],
    'segments_expected':len(chapter['chunks']),'segments_included':len(indices),
    'starts_with_segment':f'{key}-01','full_script_reconstruction_verified':True,
    'complete_audio_decode_verified':True,'source_ranges':coverage
}
(ROOT/'chapters'/f'{key} - Complete chapter verification.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
progress=ROOT/'Audiobook progress.md'
with progress.open('a',encoding='utf-8') as f:
    f.write(f'\n## Complete Chapter {int(key)} recording\n\n')
    f.write(f'**{output.name}** — all {len(indices)} segments, from {key}-01 through {key}-{len(indices):02}, in order. This single chapter file includes the opening that previously appeared in an earlier installment.\n')
minutes=int(final_duration)//60
seconds=int(final_duration)%60
print(json.dumps({
    'file':str(output),'duration_seconds':final_duration,'duration':f'{minutes}:{seconds:02}',
    'segments_included':len(indices),'first_segment':f'{key}-01','last_segment':f'{key}-{len(indices):02}',
    'coverage':coverage,'complete_audio_decode_verified':True,'next_position':m['next_position'],
    'size_bytes':output.stat().st_size
},indent=2,ensure_ascii=False))
