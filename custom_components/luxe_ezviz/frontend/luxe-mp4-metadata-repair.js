/**
 * Conservative, zero-remux MP4 metadata repair for EZUIKit recording Blobs.
 * Only repairs zero-valued VisualSampleEntry/tkhd dimensions when a matching
 * AVC/HEVC SPS provides an unambiguous coded display size. All other files are
 * returned byte-for-byte unchanged.
 */
const MAX_MOOV_BYTES=32*1024*1024,MAX_TOP_LEVEL_BOXES=10000;
const IDENTITY_MATRIX=[65536,0,0,0,65536,0,0,0,1073741824];
const AVC_ENTRIES=new Set(['avc1','avc3']),HEVC_ENTRIES=new Set(['hvc1','hev1']);
function readU16(v,o){if(o<0||o+2>v.byteLength)throw Error('mp4_truncated_u16');return v.getUint16(o,false);}
function readU32(v,o){if(o<0||o+4>v.byteLength)throw Error('mp4_truncated_u32');return v.getUint32(o,false);}
function parseBoxes(v,start,end){
 const out=[];let p=start;
 while(p<end){
  if(p+8>end)throw Error('mp4_truncated_box_header');
  const s32=readU32(v,p),type=String.fromCharCode(v.getUint8(p+4),v.getUint8(p+5),v.getUint8(p+6),v.getUint8(p+7));
  let h=8,s=s32;
  if(s32===1){if(p+16>end)throw Error('mp4_truncated_extended_header');const wide=(BigInt(readU32(v,p+8))<<32n)|BigInt(readU32(v,p+12));if(wide>BigInt(Number.MAX_SAFE_INTEGER))throw Error('mp4_box_too_large');s=Number(wide);h=16;}
  else if(s32===0)s=end-p;
  if(!Number.isSafeInteger(s)||s<h||p+s>end)throw Error('mp4_invalid_box_size');
  out.push({type,start:p,size:s,headerSize:h,payloadStart:p+h,end:p+s});p+=s;
 }
 return out;
}
async function findMoov(blob){
 let p=0,ftyp=false;
 for(let i=0;p+8<=blob.size&&i<MAX_TOP_LEVEL_BOXES;i++){
  const v=new DataView(await blob.slice(p,p+8).arrayBuffer()),s32=v.getUint32(0,false);
  const type=String.fromCharCode(v.getUint8(4),v.getUint8(5),v.getUint8(6),v.getUint8(7));
  let h=8,s=s32;
  if(s32===1){if(p+16>blob.size)throw Error('mp4_truncated_extended_header');const x=new DataView(await blob.slice(p+8,p+16).arrayBuffer());const wide=(BigInt(x.getUint32(0,false))<<32n)|BigInt(x.getUint32(4,false));if(wide>BigInt(Number.MAX_SAFE_INTEGER))throw Error('mp4_box_too_large');s=Number(wide);h=16;}
  else if(s32===0)s=blob.size-p;
  if(!Number.isSafeInteger(s)||s<h||p+s>blob.size)throw Error('mp4_invalid_top_level_box');
  if(type==='ftyp')ftyp=true;
  if(type==='moov')return {start:p,size:s,foundFtyp:ftyp};
  p+=s;if(s32===0)break;
 }
 return null;
}
class BitReader{
 constructor(bytes){this.bytes=bytes;this.bitOffset=0;}
 readBit(){if(this.bitOffset>=this.bytes.length*8)throw Error('sps_truncated');const x=(this.bytes[this.bitOffset>>3]>>(7-(this.bitOffset&7)))&1;this.bitOffset++;return x;}
 readBits(n){if(!Number.isInteger(n)||n<0||n>32)throw Error('sps_invalid_bit_count');let x=0;for(let i=0;i<n;i++)x=x*2+this.readBit();return x;}
 skipBits(n){if(!Number.isInteger(n)||n<0||this.bitOffset+n>this.bytes.length*8)throw Error('sps_truncated');this.bitOffset+=n;}
 readUE(){let z=0;while(this.readBit()===0){if(++z>31)throw Error('sps_exp_golomb_overflow');}return 2**z-1+this.readBits(z);}
 readSE(){const n=this.readUE();return n&1?(n+1)/2:-(n/2);}
}
function toRbsp(nal,headerBytes){
 if(!(nal instanceof Uint8Array)||nal.length<=headerBytes)throw Error('sps_empty_nal');
 const out=[];let zeros=0;
 for(let i=headerBytes;i<nal.length;i++){const b=nal[i];if(zeros>=2&&b===3)continue;out.push(b);zeros=b===0?Math.min(zeros+1,2):0;}
 return new Uint8Array(out);
}
function skipScalingList(r,size){let last=8,next=8;for(let j=0;j<size;j++){if(next!==0)next=(last+r.readSE()+256)%256;last=next===0?last:next;}}
function parseAvcSps(nal){
 if(nal.length<4||(nal[0]&31)!==7)throw Error('avc_sps_nal_invalid');
 const r=new BitReader(toRbsp(nal,1)),profile=r.readBits(8);r.skipBits(8);r.skipBits(8);r.readUE();
 let chroma=1,separate=0;
 if(new Set([44,83,86,100,110,118,122,128,134,135,138,139,144,244]).has(profile)){
  chroma=r.readUE();if(chroma>3)throw Error('avc_chroma_format_invalid');if(chroma===3)separate=r.readBit();
  r.readUE();r.readUE();r.readBit();
  if(r.readBit()){const count=chroma===3?12:8;for(let i=0;i<count;i++)if(r.readBit())skipScalingList(r,i<6?16:64);}
 }
 r.readUE();const poc=r.readUE();
 if(poc===0)r.readUE();
 else if(poc===1){r.readBit();r.readSE();r.readSE();const n=r.readUE();if(n>256)throw Error('avc_poc_cycle_too_large');for(let i=0;i<n;i++)r.readSE();}
 else if(poc!==2)throw Error('avc_poc_type_invalid');
 r.readUE();r.readBit();const wMbs=r.readUE()+1,hMap=r.readUE()+1,frameOnly=r.readBit();if(!frameOnly)r.readBit();r.readBit();
 let l=0,rr=0,t=0,b=0;if(r.readBit()){l=r.readUE();rr=r.readUE();t=r.readUE();b=r.readUE();}
 const codedWidth=wMbs*16,codedHeight=(2-frameOnly)*hMap*16,arrayType=separate?0:chroma;
 const subW=arrayType===1||arrayType===2?2:1,subH=arrayType===1?2:1;
 const cropX=arrayType===0?1:subW,cropY=arrayType===0?(2-frameOnly):subH*(2-frameOnly);
 const width=codedWidth-(l+rr)*cropX,height=codedHeight-(t+b)*cropY;
 if(!Number.isSafeInteger(width)||!Number.isSafeInteger(height)||width<=0||height<=0||width>65535||height>65535)throw Error('avc_dimensions_invalid');
 return {width,height,codedWidth,codedHeight,codec:'h264'};
}
function parseHevcSps(nal){
 if(nal.length<4||((nal[0]>>1)&63)!==33)throw Error('hevc_sps_nal_invalid');
 const r=new BitReader(toRbsp(nal,2));r.skipBits(4);const maxSub=r.readBits(3);if(maxSub>6)throw Error('hevc_sub_layers_invalid');r.readBit();r.skipBits(96);
 const profile=[],level=[];for(let i=0;i<maxSub;i++){profile.push(r.readBit());level.push(r.readBit());}
 if(maxSub>0)for(let i=maxSub;i<8;i++)r.skipBits(2);
 for(let i=0;i<maxSub;i++){if(profile[i])r.skipBits(88);if(level[i])r.skipBits(8);}
 r.readUE();const chroma=r.readUE();if(chroma>3)throw Error('hevc_chroma_format_invalid');const separate=chroma===3?r.readBit():0;
 const codedWidth=r.readUE(),codedHeight=r.readUE();let l=0,rr=0,t=0,b=0;
 if(r.readBit()){l=r.readUE();rr=r.readUE();t=r.readUE();b=r.readUE();}
 const arrayType=separate?0:chroma,subW=arrayType===1||arrayType===2?2:1,subH=arrayType===1?2:1;
 const width=codedWidth-subW*(l+rr),height=codedHeight-subH*(t+b);
 if(!Number.isSafeInteger(width)||!Number.isSafeInteger(height)||width<=0||height<=0||width>65535||height>65535)throw Error('hevc_dimensions_invalid');
 return {width,height,codedWidth,codedHeight,codec:'h265'};
}
function extractAvcSps(config){
 const v=new DataView(config.buffer,config.byteOffset,config.byteLength);if(config.length<7||v.getUint8(0)!==1)throw Error('avcc_invalid');
 const count=v.getUint8(5)&31;let p=6;
 for(let i=0;i<count;i++){const n=readU16(v,p);p+=2;if(!n||p+n>config.length)throw Error('avcc_sps_length_invalid');const nal=config.subarray(p,p+n);if((nal[0]&31)===7)return parseAvcSps(nal);p+=n;}
 throw Error('avcc_sps_missing');
}
function extractHevcSps(config){
 const v=new DataView(config.buffer,config.byteOffset,config.byteLength);if(config.length<23||v.getUint8(0)!==1)throw Error('hvcc_invalid');
 const arrays=v.getUint8(22);let p=23;
 for(let i=0;i<arrays;i++){if(p+3>config.length)throw Error('hvcc_array_truncated');const type=v.getUint8(p)&63,count=readU16(v,p+1);p+=3;
  for(let j=0;j<count;j++){const n=readU16(v,p);p+=2;if(!n||p+n>config.length)throw Error('hvcc_sps_length_invalid');const nal=config.subarray(p,p+n);if(type===33&&((nal[0]>>1)&63)===33)return parseHevcSps(nal);p+=n;}
 }
 throw Error('hvcc_sps_missing');
}
function getVideoHandler(view,trak){
 const mdia=parseBoxes(view,trak.payloadStart,trak.end).find(x=>x.type==='mdia');if(!mdia)return null;
 const children=parseBoxes(view,mdia.payloadStart,mdia.end),hdlr=children.find(x=>x.type==='hdlr');
 if(!hdlr||hdlr.payloadStart+12>hdlr.end)return null;
 const type=String.fromCharCode(view.getUint8(hdlr.payloadStart+8),view.getUint8(hdlr.payloadStart+9),view.getUint8(hdlr.payloadStart+10),view.getUint8(hdlr.payloadStart+11));
 return {mdia,children,type};
}
function sameMatrix(v,p){if(p+36>v.byteLength)return false;for(let i=0;i<9;i++)if(v.getInt32(p+i*4,false)!==IDENTITY_MATRIX[i])return false;return true;}
function u16bytes(n){const b=new Uint8Array(2);new DataView(b.buffer).setUint16(0,n,false);return b;}
function u32bytes(n){const b=new Uint8Array(4);new DataView(b.buffer).setUint32(0,n,false);return b;}
function result(blob,status,details={}){return {blob,status,...details};}

/** Inspect an MP4 Blob. Only unambiguous zero dimensions are repaired. */
export async function repairMp4Metadata(blob){
 if(!(blob instanceof Blob)||blob.size<16)return result(blob,'invalid',{reason:'blob_invalid'});
 try{
  const info=await findMoov(blob);if(!info||!info.foundFtyp)return result(blob,'skipped',{reason:'mp4_structure_not_found'});
  if(info.size>MAX_MOOV_BYTES)return result(blob,'skipped',{reason:'moov_too_large'});
  const bytes=new Uint8Array(await blob.slice(info.start,info.start+info.size).arrayBuffer());
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),moov=parseBoxes(view,0,view.byteLength).find(x=>x.type==='moov');
  if(!moov)return result(blob,'skipped',{reason:'moov_missing'});
  const children=parseBoxes(view,moov.payloadStart,moov.end),traks=children.filter(x=>x.type==='trak'),videos=[];
  for(const trak of traks){const h=getVideoHandler(view,trak);if(h?.type==='vide')videos.push({trak,...h});}
  if(videos.length!==1)return result(blob,'skipped',{reason:'video_track_count_unsupported'});
  const {trak,mdia,children:mdiaChildren}=videos[0],tkhd=parseBoxes(view,trak.payloadStart,trak.end).find(x=>x.type==='tkhd'),minf=mdiaChildren.find(x=>x.type==='minf');
  if(!tkhd||!minf)return result(blob,'skipped',{reason:'video_track_header_missing'});
  const version=view.getUint8(tkhd.payloadStart),trackOffset=tkhd.payloadStart+(version===0?76:version===1?88:-1000000),matrixOffset=tkhd.payloadStart+(version===0?40:version===1?52:-1000000);
  if(trackOffset<tkhd.payloadStart||trackOffset+8>tkhd.end||!sameMatrix(view,matrixOffset))return result(blob,'skipped',{reason:'track_display_geometry_unsupported'});
  const minfChildren=parseBoxes(view,minf.payloadStart,minf.end),stbl=minfChildren.find(x=>x.type==='stbl');
  if(!stbl)return result(blob,'skipped',{reason:'sample_table_missing'});
  const stsd=parseBoxes(view,stbl.payloadStart,stbl.end).find(x=>x.type==='stsd');
  if(!stsd||stsd.payloadStart+8>stsd.end)return result(blob,'skipped',{reason:'sample_description_missing'});
  if(readU32(view,stsd.payloadStart+4)!==1)return result(blob,'skipped',{reason:'sample_description_count_unsupported'});
  const entries=parseBoxes(view,stsd.payloadStart+8,stsd.end);if(entries.length!==1)return result(blob,'skipped',{reason:'sample_entry_invalid'});
  const entry=entries[0],isAvc=AVC_ENTRIES.has(entry.type),isHevc=HEVC_ENTRIES.has(entry.type);
  if(!isAvc&&!isHevc)return result(blob,'skipped',{reason:'codec_unsupported',codec:entry.type});
  if(entry.payloadStart+78>entry.end)return result(blob,'skipped',{reason:'visual_sample_entry_truncated'});
  const sampleChildren=parseBoxes(view,entry.payloadStart+78,entry.end);
  if(sampleChildren.some(x=>x.type==='clap'||x.type==='pasp'))return result(blob,'skipped',{reason:'clean_aperture_or_pixel_aspect_present',codec:entry.type});
  const configBox=sampleChildren.find(x=>x.type===(isAvc?'avcC':'hvcC'));
  if(!configBox)return result(blob,'skipped',{reason:'codec_configuration_missing',codec:entry.type});
  const config=bytes.subarray(configBox.payloadStart,configBox.end),dims=isAvc?extractAvcSps(config):extractHevcSps(config),{width,height,codec}=dims;
  const ew=entry.payloadStart+24,eh=entry.payloadStart+26,currentEW=readU16(view,ew),currentEH=readU16(view,eh);
  const currentTW=readU32(view,trackOffset),currentTH=readU32(view,trackOffset+4),expectedTW=width*65536,expectedTH=height*65536;
  if((currentEW!==0&&currentEW!==width)||(currentEH!==0&&currentEH!==height)||(currentTW!==0&&currentTW!==expectedTW)||(currentTH!==0&&currentTH!==expectedTH)){
   return result(blob,'skipped',{reason:'nonzero_dimension_conflicts_with_sps',codec,width,height,sampleEntry:[currentEW,currentEH],trackHeader:[currentTW/65536,currentTH/65536]});
  }
  const patches=[];
  if(currentEW===0)patches.push({offset:info.start+ew,bytes:u16bytes(width)});
  if(currentEH===0)patches.push({offset:info.start+eh,bytes:u16bytes(height)});
  if(currentTW===0)patches.push({offset:info.start+trackOffset,bytes:u32bytes(expectedTW)});
  if(currentTH===0)patches.push({offset:info.start+trackOffset+4,bytes:u32bytes(expectedTH)});
  if(!patches.length)return result(blob,'unchanged',{reason:'dimensions_already_consistent',codec,width,height});
  patches.sort((a,b)=>a.offset-b.offset);const parts=[];let cursor=0;
  for(const patch of patches){if(patch.offset<cursor||patch.offset+patch.bytes.length>blob.size)return result(blob,'skipped',{reason:'patch_range_invalid',codec,width,height});if(patch.offset>cursor)parts.push(blob.slice(cursor,patch.offset));parts.push(patch.bytes);cursor=patch.offset+patch.bytes.length;}
  if(cursor<blob.size)parts.push(blob.slice(cursor));
  const repaired=new Blob(parts,{type:blob.type||'video/mp4'});
  if(repaired.size!==blob.size)return result(blob,'skipped',{reason:'file_size_changed',codec,width,height});
  return result(repaired,'repaired',{reason:'zero_dimensions_repaired',codec,width,height,fields:patches.map(x=>x.bytes.length)});
 }catch(error){return result(blob,'skipped',{reason:error?.message||'metadata_repair_failed'});}
}
