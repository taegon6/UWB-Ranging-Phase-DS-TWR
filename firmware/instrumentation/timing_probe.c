#include "timing_probe.h"

static uint8_t timing_probe_has_valid_storage(const timing_probe_t *probe)
{
    return (uint8_t)((probe != NULL) &&
                     (probe->storage != NULL) &&
                     (probe->capacity > (size_t)0) &&
                     (probe->clock_now != NULL));
}

void timing_probe_init(timing_probe_t *probe,
                       timing_probe_record_t *storage,
                       size_t capacity,
                       timing_probe_clock_fn clock_now,
                       void *clock_context)
{
    if (probe == NULL) {
        return;
    }

    probe->storage = storage;
    probe->capacity = capacity;
    probe->count = (size_t)0;
    probe->dropped_records = 0u;
    probe->next_sequence = 0u;
    probe->clock_now = clock_now;
    probe->clock_context = clock_context;
    probe->enabled = timing_probe_has_valid_storage(probe);
}

void timing_probe_reset(timing_probe_t *probe)
{
    if (probe == NULL) {
        return;
    }

    probe->enabled = 0u;
    probe->count = (size_t)0;
    probe->dropped_records = 0u;
    probe->next_sequence = 0u;
    probe->enabled = timing_probe_has_valid_storage(probe);
}

void timing_probe_set_enabled(timing_probe_t *probe, uint8_t enabled)
{
    if (probe == NULL) {
        return;
    }

    probe->enabled = (uint8_t)((enabled != 0u) &&
                               (timing_probe_has_valid_storage(probe) != 0u));
}

uint8_t timing_probe_is_enabled(const timing_probe_t *probe)
{
    if (probe == NULL) {
        return 0u;
    }
    return (uint8_t)(probe->enabled != 0u);
}

uint64_t timing_probe_now(const timing_probe_t *probe)
{
    if ((probe == NULL) || (probe->clock_now == NULL)) {
        return UINT64_C(0);
    }
    return probe->clock_now(probe->clock_context);
}

timing_probe_record_status_t timing_probe_record(timing_probe_t *probe,
                                                  trace_event_t event,
                                                  trace_action_t action)
{
    size_t index;
    timing_probe_record_t *record;

    if ((probe == NULL) ||
        ((unsigned int)event >= (unsigned int)TRACE_EVENT_COUNT) ||
        ((unsigned int)action > (unsigned int)TRACE_ACTION_PULSE)) {
        return TIMING_PROBE_RECORD_INVALID;
    }

    if ((probe->enabled == 0u) || (timing_probe_has_valid_storage(probe) == 0u)) {
        return TIMING_PROBE_RECORD_DISABLED;
    }

    index = probe->count;
    if (index >= probe->capacity) {
        if (probe->dropped_records != UINT32_MAX) {
            probe->dropped_records += 1u;
        }
        return TIMING_PROBE_RECORD_FULL;
    }

    record = &probe->storage[index];
    record->timestamp_ticks = probe->clock_now(probe->clock_context);
    record->sequence = probe->next_sequence;
    record->event = (uint16_t)event;
    record->action = (uint8_t)action;
    record->reserved = 0u;

    probe->next_sequence += 1u;
    probe->count = index + (size_t)1;
    return TIMING_PROBE_RECORD_OK;
}

size_t timing_probe_count(const timing_probe_t *probe)
{
    if (probe == NULL) {
        return (size_t)0;
    }
    return probe->count;
}

uint32_t timing_probe_dropped_records(const timing_probe_t *probe)
{
    if (probe == NULL) {
        return 0u;
    }
    return probe->dropped_records;
}

const timing_probe_record_t *timing_probe_data(const timing_probe_t *probe)
{
    if (probe == NULL) {
        return NULL;
    }
    return probe->storage;
}
