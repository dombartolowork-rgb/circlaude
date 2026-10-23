#!/usr/bin/env python3
"""Pull the last N minutes out of a remote MP4 without downloading the whole file.

A 75GB camera record is `ftyp`, one enormous `mdat`, then a 13MB `moov` index at
the end. Fetch the index over an HTTP range, work out which bytes of the mdat hold
the samples you want, fetch only those, and write a fresh valid MP4 around them.

Codec configuration (`stsd`) and the track headers are copied verbatim, so the
picture and sound are byte-identical to the source. Only the sample tables are
rebuilt, renumbered to the kept samples and rebased onto the new mdat offset.

    mp4tail.py <url> <out.mp4> <tail-seconds> [--dur seconds] [--moov cached.bin]

`--dur` stops the extract that many seconds after the cut instead of running to
the end of the file, which is how you sample inside a window cheaply.

Verify every output before trusting it by opening it and watching it. A file
that muxes cleanly can still be wrong.
"""
import sys, os, struct, urllib.request, time

CHUNK = 8 * 1024 * 1024


def boxes(b, s, e):
    p = s
    while p + 8 <= e:
        sz, typ = struct.unpack('>I4s', b[p:p + 8])
        t = typ.decode('latin1'); h = 8
        if sz == 1:
            sz = struct.unpack('>Q', b[p + 8:p + 16])[0]; h = 16
        elif sz == 0:
            sz = e - p
        if sz < 8:
            break
        yield t, p + h, p + sz, p
        p += sz


def find(b, s, e, path):
    for t, bs, be, raw in boxes(b, s, e):
        if t == path[0]:
            if len(path) == 1:
                yield bs, be, raw
            else:
                yield from find(b, bs, be, path[1:])


def one(b, s, e, path):
    return next(find(b, s, e, path))


def box(typ, payload):
    return struct.pack('>I4s', len(payload) + 8, typ.encode()) + payload


def full(typ, ver_flags, payload):
    return box(typ, struct.pack('>I', ver_flags) + payload)


def http_get(url, first=None, last=None, retries=4):
    for a in range(retries):
        try:
            req = urllib.request.Request(url)
            if first is not None:
                req.add_header('Range', 'bytes=%d-%s' % (first, '' if last is None else last))
            return urllib.request.urlopen(req, timeout=120)
        except Exception as e:
            if a == retries - 1:
                raise
            time.sleep(2 ** a)


def parse_track(buf, tb, te):
    """Everything needed to rebuild one track."""
    hd = next(find(buf, tb, te, ['mdia', 'hdlr']), None)
    kind = buf[hd[0] + 8:hd[0] + 12].decode('latin1') if hd else '?'
    mdhd = one(buf, tb, te, ['mdia', 'mdhd'])
    mts, mdur = struct.unpack('>II', buf[mdhd[0] + 12:mdhd[0] + 20])
    stbl = ['mdia', 'minf', 'stbl']

    stts = one(buf, tb, te, stbl + ['stts'])
    n = struct.unpack('>I', buf[stts[0] + 4:stts[0] + 8])[0]
    deltas = []
    for i in range(n):
        c, d = struct.unpack('>II', buf[stts[0] + 8 + i * 8:stts[0] + 16 + i * 8])
        deltas.extend([d] * c)

    stsz = one(buf, tb, te, stbl + ['stsz'])
    ssz, scount = struct.unpack('>II', buf[stsz[0] + 4:stsz[0] + 12])
    sizes = [ssz] * scount if ssz else list(
        struct.unpack('>%dI' % scount, buf[stsz[0] + 12:stsz[0] + 12 + 4 * scount]))

    stsc = one(buf, tb, te, stbl + ['stsc'])
    cn = struct.unpack('>I', buf[stsc[0] + 4:stsc[0] + 8])[0]
    sc = [struct.unpack('>III', buf[stsc[0] + 8 + i * 12:stsc[0] + 20 + i * 12]) for i in range(cn)]

    co = next(find(buf, tb, te, stbl + ['stco']), None); is64 = False
    if co is None:
        co = one(buf, tb, te, stbl + ['co64']); is64 = True
    on = struct.unpack('>I', buf[co[0] + 4:co[0] + 8])[0]
    offs = list(struct.unpack('>%d%s' % (on, 'Q' if is64 else 'I'),
                              buf[co[0] + 8:co[0] + 8 + on * (8 if is64 else 4)]))

    stss = next(find(buf, tb, te, stbl + ['stss']), None)
    keys = None
    if stss:
        kn = struct.unpack('>I', buf[stss[0] + 4:stss[0] + 8])[0]
        keys = [x - 1 for x in struct.unpack('>%dI' % kn, buf[stss[0] + 8:stss[0] + 8 + 4 * kn])]

    ctts = next(find(buf, tb, te, stbl + ['ctts']), None)
    comps = None
    if ctts:
        en = struct.unpack('>I', buf[ctts[0] + 4:ctts[0] + 8])[0]
        comps = []
        for i in range(en):
            c, o = struct.unpack('>Ii', buf[ctts[0] + 8 + i * 8:ctts[0] + 16 + i * 8])
            comps.extend([o] * c)

    # absolute file offset of every sample
    sample_off = [0] * scount
    s = 0
    for ci, (fc, spc, _) in enumerate(sc):
        nextfc = sc[ci + 1][0] if ci + 1 < len(sc) else on + 1
        for c in range(fc, nextfc):
            if c - 1 >= on or s >= scount:
                break
            off = offs[c - 1]
            for _ in range(spc):
                if s >= scount:
                    break
                sample_off[s] = off
                off += sizes[s]; s += 1

    return dict(kind=kind, tb=tb, te=te, mts=mts, mdur=mdur, deltas=deltas, sizes=sizes,
                keys=keys, comps=comps, sample_off=sample_off, scount=scount)


def build(url, out_path, tail_s, moov_cache=None, want_dur=None):
    head = http_get(url, 0, 63).read()
    p = 0; moov_off = None
    while p + 8 <= len(head):
        sz, typ = struct.unpack('>I4s', head[p:p + 8]); t = typ.decode('latin1')
        if sz == 1:
            sz = struct.unpack('>Q', head[p + 8:p + 16])[0]
        if t == 'mdat':
            moov_off = p + sz; break
        p += sz
    if moov_off is None:
        raise SystemExit('no mdat in the first boxes, unexpected layout')

    if moov_cache and os.path.exists(moov_cache):
        buf = open(moov_cache, 'rb').read()
    else:
        buf = http_get(url, moov_off).read()
        if moov_cache:
            open(moov_cache, 'wb').write(buf)
    print('index %.1f MB' % (len(buf) / 1e6), flush=True)

    mv = one(buf, 0, len(buf), ['moov', 'mvhd'])
    mv_ts, mv_dur = struct.unpack('>II', buf[mv[0] + 12:mv[0] + 20])

    tracks = []
    for tb, te, raw in find(buf, 0, len(buf), ['moov', 'trak']):
        tr = parse_track(buf, tb, te)
        if tr['kind'] in ('vide', 'soun'):
            tr['raw'] = (tb, te)
            tracks.append(tr)

    # choose the cut point on the video track, snapped back to a keyframe
    vid = next(t for t in tracks if t['kind'] == 'vide')
    vdur = vid['mdur'] / vid['mts']
    target = max(0.0, vdur - tail_s)
    t_acc = 0.0; idx = 0
    for i, d in enumerate(vid['deltas']):
        if t_acc + d / vid['mts'] > target:
            idx = i; break
        t_acc += d / vid['mts']
    first_v = max([k for k in vid['keys'] if k <= idx], default=0) if vid['keys'] else idx
    cut_time = sum(vid['deltas'][:first_v]) / vid['mts']
    print('cut at %.3fs of %.3fs (keyframe %d)' % (cut_time, vdur, first_v), flush=True)

    # first sample at or after cut_time on every track
    for tr in tracks:
        if tr['kind'] == 'vide':
            tr['first'] = first_v
        else:
            acc = 0.0; f = 0
            for i, d in enumerate(tr['deltas']):
                if acc >= cut_time:
                    f = i; break
                acc += d / tr['mts']
            else:
                f = tr['scount'] - 1
            tr['first'] = f
        last = tr['scount'] - 1
        if want_dur:
            acc = 0.0
            for i in range(tr['first'], tr['scount']):
                acc += tr['deltas'][i] / tr['mts']
                if acc >= want_dur:
                    last = i; break
        tr['last'] = last
        tr['keep'] = list(range(tr['first'], last + 1))

    lo = min(tr['sample_off'][tr['first']] for tr in tracks)
    hi = max(tr['sample_off'][tr['last']] + tr['sizes'][tr['last']] for tr in tracks)
    print('byte range %d..%d = %.2f GB' % (lo, hi, (hi - lo) / 1e9), flush=True)

    # ---- build the new moov ----
    def tables(tr, mdat_base):
        keep = tr['keep']
        sizes = [tr['sizes'][i] for i in keep]
        deltas = [tr['deltas'][i] for i in keep]
        offs = [tr['sample_off'][i] - lo + mdat_base for i in keep]
        # stts, run length encoded
        runs = []
        for d in deltas:
            if runs and runs[-1][1] == d:
                runs[-1][0] += 1
            else:
                runs.append([1, d])
        stts = full('stts', 0, struct.pack('>I', len(runs)) +
                    b''.join(struct.pack('>II', c, d) for c, d in runs))
        stsz = full('stsz', 0, struct.pack('>II', 0, len(sizes)) +
                    struct.pack('>%dI' % len(sizes), *sizes))
        # one sample per chunk keeps stsc trivial and offsets exact
        stsc = full('stsc', 0, struct.pack('>I', 1) + struct.pack('>III', 1, 1, 1))
        co64 = full('co64', 0, struct.pack('>I', len(offs)) +
                    struct.pack('>%dQ' % len(offs), *offs))
        out = [stts, stsz, stsc, co64]
        if tr['keys'] is not None:
            ks = [k - tr['first'] + 1 for k in tr['keys']
                  if tr['first'] <= k <= tr['last']]
            out.append(full('stss', 0, struct.pack('>I', len(ks)) +
                            struct.pack('>%dI' % len(ks), *ks)))
        if tr['comps'] is not None:
            cs = [tr['comps'][i] for i in keep]
            cruns = []
            for o in cs:
                if cruns and cruns[-1][1] == o:
                    cruns[-1][0] += 1
                else:
                    cruns.append([1, o])
            out.append(full('ctts', 0, struct.pack('>I', len(cruns)) +
                            b''.join(struct.pack('>Ii', c, o) for c, o in cruns)))
        return out, sum(deltas)

    def rebuild_moov(mdat_base):
        traks = []
        for tr in tracks:
            tb, te = tr['raw']
            new_tables, dur_units = tables(tr, mdat_base)
            tr['new_dur'] = dur_units
            stbl_old = one(buf, tb, te, ['mdia', 'minf', 'stbl'])
            stsd = one(buf, stbl_old[0], stbl_old[1], ['stsd'])
            stsd_bytes = buf[stsd[2]:stsd[1]]
            stbl = box('stbl', stsd_bytes + b''.join(new_tables))

            minf_old = one(buf, tb, te, ['mdia', 'minf'])
            keep_minf = b''
            for t, bs, be, raw in boxes(buf, minf_old[0], minf_old[1]):
                if t != 'stbl':
                    keep_minf += buf[raw:be]
            minf = box('minf', keep_minf + stbl)

            mdhd_old = one(buf, tb, te, ['mdia', 'mdhd'])
            mdhd_bytes = bytearray(buf[mdhd_old[2]:mdhd_old[1]])
            struct.pack_into('>I', mdhd_bytes, 8 + 16, dur_units)   # +8 box hdr, +16 to duration
            hdlr_old = one(buf, tb, te, ['mdia', 'hdlr'])
            mdia = box('mdia', bytes(mdhd_bytes) + buf[hdlr_old[2]:hdlr_old[1]] + minf)

            tkhd_old = one(buf, tb, te, ['tkhd'])
            tkhd_bytes = bytearray(buf[tkhd_old[2]:tkhd_old[1]])
            new_tk_dur = int(dur_units / tr['mts'] * mv_ts)
            struct.pack_into('>I', tkhd_bytes, 8 + 20, new_tk_dur)
            traks.append(box('trak', bytes(tkhd_bytes) + mdia))

        mvhd_bytes = bytearray(buf[mv[2]:mv[1]])
        longest = max(int(t['new_dur'] / t['mts'] * mv_ts) for t in tracks)
        struct.pack_into('>I', mvhd_bytes, 8 + 16, longest)
        return box('moov', bytes(mvhd_bytes) + b''.join(traks))

    ftyp = box('ftyp', b'isom' + struct.pack('>I', 0x200) + b'isomiso2avc1mp41')
    guess = rebuild_moov(0)
    mdat_base = len(ftyp) + len(guess) + 16          # 16 = 64-bit mdat header
    moov = rebuild_moov(mdat_base)
    if len(moov) != len(guess):                       # offsets shifted the size, settle it
        mdat_base = len(ftyp) + len(moov) + 16
        moov = rebuild_moov(mdat_base)

    payload = hi - lo
    with open(out_path, 'wb') as f:
        f.write(ftyp); f.write(moov)
        f.write(struct.pack('>I4sQ', 1, b'mdat', payload + 16))
        r = http_get(url, lo, hi - 1)
        got = 0; t0 = time.time()
        while got < payload:
            b = r.read(min(CHUNK, payload - got))
            if not b:
                break
            f.write(b); got += len(b)
            if got % (256 * 1024 * 1024) < CHUNK:
                print('   %.1f/%.1f GB  %.1f MB/s' % (got / 1e9, payload / 1e9,
                      got / 1e6 / max(1, time.time() - t0)), flush=True)
    print('wrote %s  %.2f GB' % (out_path, os.path.getsize(out_path) / 1e9), flush=True)


if __name__ == '__main__':
    args = sys.argv[1:]
    cache = None
    if '--moov' in args:
        i = args.index('--moov'); cache = args[i + 1]; del args[i:i + 2]
    dur = None
    if '--dur' in args:
        i = args.index('--dur'); dur = float(args[i + 1]); del args[i:i + 2]
    build(args[0], args[1], float(args[2]), cache, dur)
