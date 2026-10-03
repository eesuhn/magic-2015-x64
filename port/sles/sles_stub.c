/*
 * Minimal silent OpenSL ES for arm32 guests under ZettaBridge, whose guest sysroot has no
 * libOpenSLES.so. In Magic 2015 only the Bink video player (BinkOpenRADSS2) uses it, for movie
 * sound; game music and effects go through FMOD and Java AudioTrack.
 *
 * Every call succeeds. Buffer queues are drained at real-time rate by one pump thread, so a caller
 * that waits on buffer-queue callbacks keeps running. No audio is produced.
 *
 * Freestanding: only pthread_create, pthread_self, usleep and clock_gettime come from bionic.
 */
typedef unsigned int u32;
typedef int s32;
typedef short s16;
typedef u32 SLresult;

#define OK 0u
#define SL_RESULT_PARAMETER_INVALID 2u
#define SL_RESULT_MEMORY_FAILURE 3u
#define SL_RESULT_BUFFER_INSUFFICIENT 7u
#define SL_RESULT_FEATURE_UNSUPPORTED 12u
#define SL_OBJECT_STATE_REALIZED 2u
#define SL_PLAYSTATE_STOPPED 1u
#define SL_PLAYSTATE_PAUSED 2u
#define SL_PLAYSTATE_PLAYING 3u
#define SL_DATAFORMAT_PCM 2u

#define MAX_OBJS 64
#define MAX_BUFS 256
#define TICK_US 10000u
#define IDLE_US 50000u

typedef struct { u32 d[4]; } IID;
typedef const IID *SLInterfaceID;

#define EXPORT __attribute__((visibility("default")))

static const IID iid_engine = {{0x8d97c260, 0xddd4, 0x11db, 0x958f}};
static const IID iid_play = {{0xef0bd9c0, 0xddd7, 0x11db, 0xbf49}};
static const IID iid_bq = {{0x2bc99cc0, 0xddd4, 0x11db, 0x8d99}};
static const IID iid_volume = {{0x09e8ede0, 0xddde, 0x11db, 0xb4f6}};
EXPORT const SLInterfaceID SL_IID_ENGINE = &iid_engine;
EXPORT const SLInterfaceID SL_IID_PLAY = &iid_play;
EXPORT const SLInterfaceID SL_IID_BUFFERQUEUE = &iid_bq;
EXPORT const SLInterfaceID SL_IID_VOLUME = &iid_volume;
EXPORT const SLInterfaceID SL_IID_ANDROIDSIMPLEBUFFERQUEUE = &iid_bq;

typedef void (*bq_cb)(void *caller, void *ctx);

/* An interface is a pointer to a vtable pointer, so each object embeds one slot per interface. */
struct obj {
    const void *obj_itf, *engine_itf, *play_itf, *bq_itf, *vol_itf;
    int used, in_callback;
    u32 state; /* SL_PLAYSTATE_* */
    u32 bytes_per_ms, queued, head;
    unsigned long long played_us; /* how far into the head buffer playback is */
    u32 sizes[MAX_BUFS];
    bq_cb cb;
    void *cb_ctx;
    s16 vol;
    u32 mute;
};

static struct obj objs[MAX_OBJS];
static volatile int lock_word;
static volatile int pump_started;
static unsigned long pump_thread;

extern int pthread_create(void *thread, const void *attr, void *(*fn)(void *), void *arg);
extern unsigned long pthread_self(void);
extern int usleep(u32 us);
struct timespec32 { s32 tv_sec; s32 tv_nsec; };
extern int clock_gettime(s32 clock, struct timespec32 *ts);
#define CLOCK_MONOTONIC 1

static unsigned long long now_us(void) {
    struct timespec32 ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (unsigned long long)(u32)ts.tv_sec * 1000000ull + (u32)ts.tv_nsec / 1000u;
}

static void lock(void) {
    while (__atomic_exchange_n(&lock_word, 1, __ATOMIC_ACQUIRE)) {}
}
static void unlock(void) { __atomic_store_n(&lock_word, 0, __ATOMIC_RELEASE); }

#define OBJ_OF(itfp, field) ((struct obj *)((char *)(itfp) - __builtin_offsetof(struct obj, field)))

/* Microseconds one buffer of `size` bytes lasts; buffers of unknown format last one tick. */
static u32 buffer_us(const struct obj *o, u32 size) {
    if (o->bytes_per_ms == 0) return TICK_US;
    return (size / o->bytes_per_ms) * 1000u + ((size % o->bytes_per_ms) * 1000u) / o->bytes_per_ms;
}

/* Plays every playing queue in real time: each pass advances them by the wall-clock time since
 * the last pass and retires every buffer that has finished, calling back once per buffer. */
static void *pump(void *unused) {
    unsigned long long last = now_us();
    (void)unused;
    for (;;) {
        int busy = 0;
        const unsigned long long now = now_us();
        const unsigned long long step = now - last;
        last = now;
        for (int i = 0; i < MAX_OBJS; i++) {
            struct obj *o = &objs[i];
            lock();
            if (o->used && o->state == SL_PLAYSTATE_PLAYING && o->queued) {
                busy = 1;
                o->played_us += step;
            }
            for (;;) {
                bq_cb cb;
                void *ctx;
                if (!(o->used && o->state == SL_PLAYSTATE_PLAYING && o->queued)) break;
                const u32 need = buffer_us(o, o->sizes[o->head]);
                if (o->played_us < need) break;
                o->played_us -= need;
                o->head = (o->head + 1) % MAX_BUFS;
                o->queued--;
                cb = o->cb;
                ctx = o->cb_ctx;
                if (!cb) continue;
                o->in_callback = 1;
                unlock();
                cb((void *)&o->bq_itf, ctx);
                lock();
                o->in_callback = 0;
            }
            unlock();
        }
        usleep(busy ? TICK_US : IDLE_US);
    }
    return 0;
}

static void start_pump(void) {
    if (__atomic_exchange_n(&pump_started, 1, __ATOMIC_ACQ_REL)) return;
    if (pthread_create(&pump_thread, 0, pump, 0) != 0) {
        __atomic_store_n(&pump_started, 0, __ATOMIC_RELEASE); /* try again on the next Play */
    }
}

static SLresult ok0(void) { return OK; }

/* --- SLObjectItf --- */
static SLresult o_realize(const void *self, u32 async) { (void)self; (void)async; return OK; }
static SLresult o_getstate(const void *self, u32 *st) { (void)self; if (st) *st = SL_OBJECT_STATE_REALIZED; return OK; }
static SLresult o_getitf(const void *self, SLInterfaceID iid, const void **out) {
    struct obj *o = OBJ_OF(self, obj_itf);
    const void **slot = 0;
    if (!out) return SL_RESULT_PARAMETER_INVALID;
    if (iid == SL_IID_ENGINE) slot = &o->engine_itf;
    else if (iid == SL_IID_PLAY) slot = &o->play_itf;
    else if (iid == SL_IID_BUFFERQUEUE) slot = &o->bq_itf;
    else if (iid == SL_IID_VOLUME) slot = &o->vol_itf;
    if (!slot || !*slot) { *out = 0; return SL_RESULT_FEATURE_UNSUPPORTED; }
    *out = slot;
    return OK;
}
static void o_destroy(const void *self) {
    struct obj *o = OBJ_OF(self, obj_itf);
    /* Wait out a callback in flight on the pump thread, unless this is that callback. */
    const int on_pump = pump_started && pthread_self() == pump_thread;
    lock();
    while (o->in_callback && !on_pump) {
        unlock();
        usleep(1000);
        lock();
    }
    o->used = 0;
    o->state = SL_PLAYSTATE_STOPPED;
    o->queued = 0;
    o->cb = 0;
    unlock();
}
static SLresult o_getprio(const void *self, s32 *p, u32 *pre) { (void)self; if (p) *p = 0; if (pre) *pre = 1; return OK; }
static const void *obj_vt[10] = {
    o_realize, o_realize /* Resume */, o_getstate, o_getitf, ok0 /* RegisterCallback */,
    ok0 /* AbortAsyncOperation */, o_destroy, ok0 /* SetPriority */, o_getprio, ok0 /* SetLossOfControlInterfaces */,
};

/* --- SLPlayItf --- */
static SLresult p_setstate(const void *self, u32 st) {
    struct obj *o = OBJ_OF(self, play_itf);
    if (st < SL_PLAYSTATE_STOPPED || st > SL_PLAYSTATE_PLAYING) return SL_RESULT_PARAMETER_INVALID;
    lock();
    o->state = st;
    if (st == SL_PLAYSTATE_STOPPED) { o->queued = 0; o->head = 0; o->played_us = 0; }  /* stop clears the queue */
    unlock();
    if (st == SL_PLAYSTATE_PLAYING) start_pump();
    return OK;
}
static SLresult p_getstate(const void *self, u32 *st) {
    struct obj *o = OBJ_OF(self, play_itf);
    if (st) *st = o->state;
    return OK;
}
static SLresult p_getu32(const void *self, u32 *v) { (void)self; if (v) *v = 0; return OK; }
static SLresult p_getdur(const void *self, u32 *v) { (void)self; if (v) *v = 0xFFFFFFFFu; return OK; }  /* SL_TIME_UNKNOWN */
static const void *play_vt[12] = {
    p_setstate, p_getstate, p_getdur, p_getu32 /* GetPosition */, ok0 /* RegisterCallback */,
    ok0 /* SetCallbackEventsMask */, p_getu32 /* GetCallbackEventsMask */, ok0 /* SetMarkerPosition */,
    ok0 /* ClearMarkerPosition */, p_getu32 /* GetMarkerPosition */, ok0 /* SetPositionUpdatePeriod */,
    p_getu32 /* GetPositionUpdatePeriod */,
};

/* --- SLBufferQueueItf --- */
static SLresult b_enqueue(const void *self, const void *buf, u32 size) {
    struct obj *o = OBJ_OF(self, bq_itf);
    SLresult r = OK;
    (void)buf;
    lock();
    if (o->queued >= MAX_BUFS) r = SL_RESULT_BUFFER_INSUFFICIENT;
    else { o->sizes[(o->head + o->queued) % MAX_BUFS] = size; o->queued++; }
    unlock();
    return r;
}
static SLresult b_clear(const void *self) {
    struct obj *o = OBJ_OF(self, bq_itf);
    lock(); o->queued = 0; o->played_us = 0; unlock();
    return OK;
}
static SLresult b_getstate(const void *self, u32 *st) {
    struct obj *o = OBJ_OF(self, bq_itf);
    if (st) { lock(); st[0] = o->queued; st[1] = o->head; unlock(); }
    return OK;
}
static SLresult b_regcb(const void *self, bq_cb cb, void *ctx) {
    struct obj *o = OBJ_OF(self, bq_itf);
    lock(); o->cb = cb; o->cb_ctx = ctx; unlock();
    return OK;
}
static const void *bq_vt[4] = { b_enqueue, b_clear, b_getstate, b_regcb };

/* --- SLVolumeItf --- */
static SLresult v_set(const void *self, s16 l) { OBJ_OF(self, vol_itf)->vol = l; return OK; }
static SLresult v_get(const void *self, s16 *l) { if (l) *l = OBJ_OF(self, vol_itf)->vol; return OK; }
static SLresult v_max(const void *self, s16 *l) { (void)self; if (l) *l = 0; return OK; }
static SLresult v_setmute(const void *self, u32 m) { OBJ_OF(self, vol_itf)->mute = m; return OK; }
static SLresult v_getmute(const void *self, u32 *m) { if (m) *m = OBJ_OF(self, vol_itf)->mute; return OK; }
static SLresult v_getu32(const void *self, u32 *v) { (void)self; if (v) *v = 0; return OK; }
static SLresult v_gets16(const void *self, s16 *v) { (void)self; if (v) *v = 0; return OK; }
static const void *vol_vt[9] = {
    v_set, v_get, v_max, v_setmute, v_getmute, ok0 /* EnableStereoPosition */,
    v_getu32 /* IsEnabledStereoPosition */, ok0 /* SetStereoPosition */, v_gets16 /* GetStereoPosition */,
};

/* engine: only the engine object exposes SLEngineItf; players and mixes expose the rest. */
static struct obj *new_obj(const void *engine_vtable) {
    struct obj *r = 0;
    lock();
    for (int i = 0; i < MAX_OBJS; i++) {
        struct obj *o = &objs[i];
        if (!o->used && !o->in_callback) {
            char *p = (char *)o;
            for (u32 k = 0; k < sizeof *o; k++) p[k] = 0;
            o->obj_itf = obj_vt;
            o->engine_itf = engine_vtable;
            if (!engine_vtable) { o->play_itf = play_vt; o->bq_itf = bq_vt; o->vol_itf = vol_vt; }
            o->state = SL_PLAYSTATE_STOPPED;
            o->used = 1;
            r = o;
            break;
        }
    }
    unlock();
    return r;
}

/* --- SLEngineItf --- */
struct data_source { const u32 *locator; const u32 *format; };

static SLresult e_player(const void *self, const void **out, const struct data_source *src) {
    struct obj *o;
    (void)self;
    if (!out) return SL_RESULT_PARAMETER_INVALID;
    o = new_obj(0);
    if (!o) return SL_RESULT_MEMORY_FAILURE;
    if (src && src->format && src->format[0] == SL_DATAFORMAT_PCM) {
        /* SLDataFormat_PCM: formatType, numChannels, samplesPerSec (milliHz), bitsPerSample, ... */
        const u32 hz = src->format[2] / 1000u;
        o->bytes_per_ms = hz * src->format[1] * (src->format[3] / 8u) / 1000u;
    }
    *out = &o->obj_itf;
    return OK;
}
static SLresult e_outmix(const void *self, const void **out) {
    struct obj *o;
    (void)self;
    if (!out) return SL_RESULT_PARAMETER_INVALID;
    o = new_obj(0);
    if (!o) return SL_RESULT_MEMORY_FAILURE;
    *out = &o->obj_itf;
    return OK;
}
static SLresult e_unsup(void) { return SL_RESULT_FEATURE_UNSUPPORTED; }
static SLresult e_qnum_itfs(const void *self, u32 id, u32 *n) { (void)self; (void)id; if (n) *n = 0; return OK; }
static SLresult e_qnum_exts(const void *self, u32 *n) { (void)self; if (n) *n = 0; return OK; }
static const void *engine_vt[15] = {
    e_unsup /* CreateLEDDevice */, e_unsup /* CreateVibraDevice */, e_player, e_unsup /* CreateAudioRecorder */,
    e_unsup /* CreateMidiPlayer */, e_unsup /* CreateListener */, e_unsup /* Create3DGroup */, e_outmix,
    e_unsup /* CreateMetadataExtractor */, e_unsup /* CreateExtensionObject */, e_qnum_itfs /* QueryNumSupportedInterfaces */,
    e_unsup /* QuerySupportedInterfaces */, e_qnum_exts /* QueryNumSupportedExtensions */,
    e_unsup /* QuerySupportedExtension */, e_unsup /* IsExtensionSupported */,
};

EXPORT SLresult slCreateEngine(const void **engine, u32 nopt, const void *opts, u32 nitf,
                               const SLInterfaceID *ids, const u32 *req) {
    struct obj *o;
    (void)nopt; (void)opts; (void)nitf; (void)ids; (void)req;
    if (!engine) return SL_RESULT_PARAMETER_INVALID;
    o = new_obj(engine_vt);
    if (!o) return SL_RESULT_MEMORY_FAILURE;
    *engine = &o->obj_itf;
    return OK;
}

EXPORT SLresult slQueryNumSupportedEngineInterfaces(u32 *n) { if (n) *n = 0; return OK; }
