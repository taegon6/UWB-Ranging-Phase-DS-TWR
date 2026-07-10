#ifndef UWB_TRACE_GPIO_H
#define UWB_TRACE_GPIO_H

#include <stddef.h>
#include <stdint.h>

#include "timing_probe.h"
#include "trace_events.h"

/*
 * Keep tracing disabled in the baseline unless the firmware build explicitly
 * opts in.  Disabled call-site macros do not evaluate their arguments.
 */
#ifndef UWB_TIMING_TRACE_ENABLE
#define UWB_TIMING_TRACE_ENABLE 0
#endif

/* Software timestamp support can be excluded independently when tracing is on. */
#ifndef UWB_TIMING_TRACE_SOFTWARE_ENABLE
#define UWB_TIMING_TRACE_SOFTWARE_ENABLE 1
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef uint16_t trace_gpio_pin_t;

#define TRACE_GPIO_PIN_UNUSED ((trace_gpio_pin_t)UINT16_MAX)

/*
 * Board callback contract: one bounded direct GPIO write only.  The callback
 * must not call printf/logging, sleep, allocate, lock, or perform bus I/O.
 */
typedef void (*trace_gpio_write_fn)(void *context,
                                    trace_gpio_pin_t pin,
                                    uint8_t level);

typedef struct {
    trace_gpio_pin_t pin;
    uint8_t active_high;
    uint8_t enabled;
} trace_gpio_route_t;

typedef struct {
    const trace_gpio_route_t *routes;
    size_t route_count;
    trace_gpio_write_fn write;
    void *write_context;
    timing_probe_t *software_probe;
    uint8_t gpio_enabled;
    uint8_t software_timestamp_enabled;
} trace_gpio_config_t;

typedef enum {
    TRACE_GPIO_CONFIG_OK = 0,
    TRACE_GPIO_CONFIG_INVALID = 1
} trace_gpio_config_status_t;

/* Configure once before enabling radio IRQs. NULL selects the null backend. */
trace_gpio_config_status_t trace_gpio_configure(const trace_gpio_config_t *config);
void trace_gpio_reset(void);
uint8_t trace_gpio_is_configured(void);

void trace_event_set(trace_event_t event);
void trace_event_clear(trace_event_t event);
void trace_event_pulse(trace_event_t event);

#ifdef __cplusplus
}
#endif

/*
 * The implementation translation unit defines UWB_TIMING_TRACE_IMPLEMENTATION
 * so it can provide linkable null functions.  Every other translation unit
 * gets zero-cost, non-evaluating calls when tracing is disabled.
 */
#if !UWB_TIMING_TRACE_ENABLE && !defined(UWB_TIMING_TRACE_IMPLEMENTATION)
#define trace_event_set(event_) ((void)0)
#define trace_event_clear(event_) ((void)0)
#define trace_event_pulse(event_) ((void)0)
#endif

#if UWB_TIMING_TRACE_ENABLE
#define UWB_TRACE_SET(event_) trace_event_set((event_))
#define UWB_TRACE_CLEAR(event_) trace_event_clear((event_))
#define UWB_TRACE_PULSE(event_) trace_event_pulse((event_))
#else
#define UWB_TRACE_SET(event_) ((void)0)
#define UWB_TRACE_CLEAR(event_) ((void)0)
#define UWB_TRACE_PULSE(event_) ((void)0)
#endif

#endif /* UWB_TRACE_GPIO_H */
