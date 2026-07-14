#ifndef UWB_TIMING_PROBE_H
#define UWB_TIMING_PROBE_H

#include <stddef.h>
#include <stdint.h>

#include "trace_events.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * The clock callback must be monotonic, bounded, and safe in every context in
 * which timing_probe_record() is called.  It must not perform I/O or block.
 */
typedef uint64_t (*timing_probe_clock_fn)(void *context);

typedef struct {
    uint64_t timestamp_ticks;
    uint32_t sequence;
    uint16_t event;
    uint8_t action;
    uint8_t reserved;
} timing_probe_record_t;

typedef enum {
    TIMING_PROBE_RECORD_OK = 0,
    TIMING_PROBE_RECORD_DISABLED = 1,
    TIMING_PROBE_RECORD_FULL = 2,
    TIMING_PROBE_RECORD_INVALID = 3
} timing_probe_record_status_t;

/*
 * Append-only fixed-storage recorder.  It allocates no memory, performs no
 * logging, and never waits for a consumer.  Configure/reset/drain it outside
 * the RF/ISR path.  Calls to timing_probe_record() must be serialized by the
 * integration (normally one ISR/RF producer); this portable C null backend
 * deliberately makes no target-specific atomicity assumption.
 */
typedef struct {
    timing_probe_record_t *storage;
    size_t capacity;
    volatile size_t count;
    volatile uint32_t dropped_records;
    volatile uint32_t next_sequence;
    timing_probe_clock_fn clock_now;
    void *clock_context;
    volatile uint8_t enabled;
} timing_probe_t;

void timing_probe_init(timing_probe_t *probe,
                       timing_probe_record_t *storage,
                       size_t capacity,
                       timing_probe_clock_fn clock_now,
                       void *clock_context);

void timing_probe_reset(timing_probe_t *probe);
void timing_probe_set_enabled(timing_probe_t *probe, uint8_t enabled);
uint8_t timing_probe_is_enabled(const timing_probe_t *probe);

uint64_t timing_probe_now(const timing_probe_t *probe);

timing_probe_record_status_t timing_probe_record(timing_probe_t *probe,
                                                  trace_event_t event,
                                                  trace_action_t action);

size_t timing_probe_count(const timing_probe_t *probe);
uint32_t timing_probe_dropped_records(const timing_probe_t *probe);
const timing_probe_record_t *timing_probe_data(const timing_probe_t *probe);

#ifdef __cplusplus
}
#endif

#endif /* UWB_TIMING_PROBE_H */
