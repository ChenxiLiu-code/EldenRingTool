from __future__ import annotations
import hashlib, struct, time
from dataclasses import dataclass
from pathlib import Path

try:
    from Crypto.Cipher import AES
except Exception:  # surfaced only if an encrypted save is encountered
    AES = None

ER_SAVE_KEY = bytes([0x18,0xF6,0x32,0x66,0x05,0xBD,0x17,0x8A,0x55,0x24,0x52,0x3A,0xC0,0xA0,0xC6,0x09])
EF_LEN=0x1BF99F; FLAG_DIVISOR=1000; BLOCK_SIZE=125
HDR={"ACTIVE":0x1954,"NAME0":0x195e,"STRIDE":0x24c,"NAME_BYTES":0x22,"LEVEL":0x22,"SECONDS":0x26}

class SaveError(RuntimeError): pass

def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def i32(b,o): return struct.unpack_from('<i',b,o)[0]
def f32(b,o): return struct.unpack_from('<f',b,o)[0]

def read_bnd4(buf: bytes):
    if len(buf)<0x40 or buf[:4]!=b'BND4': raise SaveError('不是 Elden Ring BND4 存档')
    n=u32(buf,0x0c)
    if not 0<n<=256: raise SaveError(f'BND4 条目数量异常: {n}')
    table_end=0x40+n*0x20
    if table_end>len(buf): raise SaveError('BND4 目录被截断')
    out=[]
    for idx in range(n):
        o=0x40+idx*0x20; size=struct.unpack_from('<Q',buf,o+8)[0]; data=u32(buf,o+0x10); nameo=u32(buf,o+0x14)
        if nameo>=len(buf) or nameo%2: raise SaveError('BND4 名称偏移异常')
        e=nameo
        while e+1<len(buf) and buf[e:e+2]!=b'\0\0': e+=2
        if e+1>=len(buf): raise SaveError('BND4 名称未终止')
        if data+size>len(buf): raise SaveError('BND4 数据条目越界')
        out.append({"index":idx,"name":buf[nameo:e].decode('utf-16le','replace'),"size":size,"dataOffset":data})
    return out

def entry_payload(buf: bytes, ent: dict):
    block=buf[ent['dataOffset']:ent['dataOffset']+ent['size']]
    if len(block)<32: raise SaveError(f"{ent['name']}: 条目过小")
    body=block[16:]
    if hashlib.md5(body).digest()==block[:16]: return body,False,True
    if AES is None: raise SaveError('该存档使用 AES 加密，但未安装 pycryptodome')
    if len(block[16:])%16: raise SaveError(f"{ent['name']}: AES 密文长度异常")
    pt=AES.new(ER_SAVE_KEY,AES.MODE_CBC,iv=block[:16]).decrypt(block[16:])
    if len(pt)<16: raise SaveError(f"{ent['name']}: AES 解密结果异常")
    return pt[16:],True,hashlib.md5(pt[16:]).digest()==pt[:16]

def read_stable(path: Path, tries=15, wait=0.08):
    for _ in range(tries):
        try:
            b=path.read_bytes(); ents=read_bnd4(b)
            if all(entry_payload(b,e)[2] for e in ents): return b
        except (OSError,SaveError,ValueError): pass
        time.sleep(wait)
    return None

def _utf16z(b,o,n):
    end=min(o+n,len(b)-1); e=o
    while e+1<end and b[e:e+2]!=b'\0\0': e+=2
    return b[o:e].decode('utf-16le','replace')

def read_profiles(payload):
    out=[]
    for slot in range(10):
        n=HDR['NAME0']+slot*HDR['STRIDE']
        if n+HDR['SECONDS']+4>len(payload): break
        out.append({"slot":slot,"active":payload[HDR['ACTIVE']+slot]==1,"name":_utf16z(payload,n,HDR['NAME_BYTES']),
                    "level":u32(payload,n+HDR['LEVEL']),"secondsPlayed":u32(payload,n+HDR['SECONDS'])})
    return out

def load_flag_groups(path: Path):
    out={}
    for line in path.read_text(encoding='utf-8').splitlines():
        if ',' in line:
            a,b=line.split(',',1); out[int(a)]=int(b)
    return out

class EventFlags:
    def __init__(self,pay,offset,groups): self.pay=pay; self.offset=offset; self.groups=groups
    def get(self,flag_id):
        block,index=divmod(int(flag_id),FLAG_DIVISOR); group=self.groups.get(block)
        if group is None:return None
        byte=self.offset+group*BLOCK_SIZE+index//8
        if byte>=len(self.pay):return None
        return ((self.pay[byte]>>(7-(index&7)))&1)==1

def walk_slot(pay: bytes):
    version=u32(pay,0); p=0x20; gaitems={}
    for _ in range(0x1400 if version>81 else 0x13fe):
        handle,item=u32(pay,p),u32(pay,p+4)
        if handle not in (0,0xffffffff) and item!=0xffffffff:gaitems[handle]={"handle":handle,"itemId":item}
        p+=8
        if handle:
            top=handle&0xf0000000
            if top==0x80000000:p+=13
            elif top==0x90000000:p+=8
    player=p; p+=0x1b0+0xd*0x10+0x58+0x1c+0x58+0x58
    held=p; p+=4+0xa80*12+4+0x180*12+8
    p+=14*8+4; p+=0xa*8+4+6*8+8; p+=6*4; p+=4+u32(pay,p)*8; p+=0x27*4+0xc
    if pay[p+4:p+8] not in (b'FACE',b'\0\0\0\0'):raise SaveError(f'FaceData magic mismatch @0x{p:x}')
    p+=0x12f; storage=p; p+=4+0x780*12+4+0x80*12+8; gestures=p; p+=0x40*4
    region_count=u32(pay,p); p+=4+region_count*4+0x28
    if pay[p]>1:raise SaveError(f'control byte @0x{p:x}={pay[p]}')
    p+=1+0x44+8; p+=8+u32(pay,p+4); p+=0x34+8+7000*0x10
    tsize,tcount=u32(pay,p+4),u32(pay,p+8); p+=8+(4 if tcount==0 else 4+((tsize-4)//4)*4)
    p+=3; deaths=u32(pay,p);p+=4; character_type=i32(pay,p);p+=4; p+=1
    online=u32(pay,p)
    if online not in (0,8):raise SaveError(f'character_type_online={online}')
    p+=4; grace=u32(pay,p);p+=4; p+=1+4+4
    if p+EF_LEN>=len(pay) or pay[p+EF_LEN]!=0:raise SaveError('event-flag terminator mismatch')
    return {"version":version,"playerGameData":player,"eventFlags":p,"deaths":deaths,"characterType":character_type,
            "lastRestedGrace":grace,"regionCount":region_count,"gaItems":gaitems,"inventoryHeld":held,
            "inventoryStorage":storage,"gestures":gestures}

def read_character(pay,w):
    g=w['playerGameData']; e=g+0x94; limit=e+32
    while e+1<limit and pay[e:e+2]!=b'\0\0':e+=2
    return {"hp":u32(pay,g+8),"maxHp":u32(pay,g+0xc),"fp":u32(pay,g+0x14),"maxFp":u32(pay,g+0x18),
            "stamina":u32(pay,g+0x24),"maxStamina":u32(pay,g+0x28),"vigor":u32(pay,g+0x34),"mind":u32(pay,g+0x38),
            "endurance":u32(pay,g+0x3c),"strength":u32(pay,g+0x40),"dexterity":u32(pay,g+0x44),
            "intelligence":u32(pay,g+0x48),"faith":u32(pay,g+0x4c),"arcane":u32(pay,g+0x50),"level":u32(pay,g+0x60),
            "runes":u32(pay,g+0x64),"runesMemory":u32(pay,g+0x68),"name":pay[g+0x94:e].decode('utf-16le','replace'),"deaths":w['deaths']}

def read_position(pay,w):
    p=w['eventFlags']+EF_LEN+1
    p+=4+max(0,i32(pay,p)); p+=4+max(0,i32(pay,p))
    for _ in range(2):
        p+=12
        while True:
            esize=i32(pay,p+4)
            if esize<=0:p+=16;break
            p+=16+(esize-0x10)
    p+=4+max(0,i32(pay,p)); mid=pay[p+12:p+16]
    return {"x":f32(pay,p),"y":f32(pay,p+4),"z":f32(pay,p+8),"mapId":f"m{mid[3]:02d}_{mid[2]:02d}_{mid[1]:02d}_{mid[0]:02d}","mapBytes":list(mid)}

def read_inventory(pay,w):
    totals={}; unknown=0
    typemap={0x80000000:'weapon',0x90000000:'protector',0xa0000000:'accessory',0xb0000000:'goods',0xc0000000:'gem'}
    def add(handle,q,where):
        nonlocal unknown
        if handle in (0,0xffffffff) or not q:return
        typ=typemap.get(handle&0xf0000000)
        if not typ:unknown+=1;return
        # Goods and talismans encode the Param ID directly; only instanced
        # equipment (weapons, armour, ashes of war) needs the GaItem table.
        if typ in ('goods', 'accessory'):
            raw=handle
        else:
            gi=w['gaItems'].get(handle)
            if not gi:unknown+=1;return
            raw=gi['itemId']
        ident=raw&0x0fffffff; key=f'{typ}:{ident}'
        row=totals.setdefault(key,{"type":typ,"rawId":raw,"id":ident,"quantity":0,"held":0,"storage":0})
        row['quantity']+=q;row[where]+=q
    def scan(off,common,keycap,where):
        p=off; common_count=u32(pay,p);p+=4
        for _ in range(common):add(u32(pay,p),u32(pay,p+4),where);p+=12
        key_count=u32(pay,p);p+=4
        for _ in range(keycap):add(u32(pay,p),u32(pay,p+4),where);p+=12
        return {"commonCount":common_count,"keyCount":key_count}
    held=scan(w['inventoryHeld'],0xa80,0x180,'held'); storage=scan(w['inventoryStorage'],0x780,0x80,'storage')
    return {"items":list(totals.values()),"held":held,"storage":storage,"unknownHandles":unknown}

def read_gestures(pay,w):
    seen=set();out=[]
    for n in range(0x40):
        ident=i32(pay,w['gestures']+n*4)
        if ident<=0 or ident==0xfe:continue
        ident=ident if ident&1 else ident+1
        if ident not in seen:seen.add(ident);out.append(ident)
    return sorted(out)

class SaveReader:
    def __init__(self,path: str|Path,bst_path: str|Path): self.path=Path(path); self.groups=load_flag_groups(Path(bst_path))
    def read(self):
        buf=read_stable(self.path)
        if buf is None:raise SaveError(f'无法稳定读取存档: {self.path}')
        entries=read_bnd4(buf); by={e['name']:e for e in entries}; header=by.get('USER_DATA010') or entries[10]
        hp,encrypted,ok=entry_payload(buf,header)
        chars=[]
        for pr in read_profiles(hp):
            if not pr['active']:continue
            ent=by.get(f"USER_DATA{pr['slot']:03d}") or (entries[pr['slot']] if pr['slot']<len(entries) else None)
            if not ent:continue
            pay,enc,checksum=entry_payload(buf,ent); c={**pr,"checksumOk":checksum,"encrypted":enc}
            try:
                w=walk_slot(pay); c['stats']=read_character(pay,w); c['deaths']=w['deaths'];c['lastRestedGrace']=w['lastRestedGrace'];c['regionCount']=w['regionCount']
                try:c['position']=read_position(pay,w)
                except Exception:c['position']=None
                c['_flags']=EventFlags(pay,w['eventFlags'],self.groups);c['_inventoryRaw']=read_inventory(pay,w);c['_gestureIds']=read_gestures(pay,w);c['flagOffset']=w['eventFlags'];c['ok']=True
            except Exception as e:c['ok']=False;c['error']=str(e)
            chars.append(c)
        return {"encrypted":encrypted,"characters":chars}
