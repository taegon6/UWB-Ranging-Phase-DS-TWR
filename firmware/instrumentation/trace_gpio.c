#define UWB_TIMING_TRACE_IMPLEMENTATION 1
#include "trace_gpio.h"

static trace_gpio_config_t g_trace_config;
static uint8_t g_trace_configured;

static void trace_gpio_clear_config(void)
{
    g_trace_config.routes = NULL;
    g_trace_config.route_count = (size_t)0;
    g_trace_config.write = NULL;
    g_trace_config.write_context = NULL;
    g_trace_config.software_probe = NULL;
    g_trace_config.gpio_enabled = 0u;
    g_trace_config.software_timestamp_enabled = 0u;
    g_trace_configured = 0u;
}

trace_gpio_config_status_t trace_gpio_configure(const trace_gpio_config_t *config)
{
    if (config == NULL) {
        trace_gpio_clear_config();
        return TRACE_GPIO_CONFIG_OK;
    }

    if (((config->route_count > (size_t)0) && (config->routes == NULL)) ||
        (config->route_count > (size_t)TRACE_EVENT_COUNT) ||
        ((config->gpio_enabled != 0u) && (config->write == NULL)) ||
        ((config->software_timestamp_enabled != 0u) &&
         (config->software_probe == NULL))) {
        /* Fail closed so a rejected reconfiguration cannot retain stale pins. */
        trace_gpio_clear_config();
        return TRACE_GPIO_CONFIG_INVALID;
    }

    g_trace_config = *config;
    g_trace_config.gpio_enabled = (uint8_t)(config->gpio_enabled != 0u);
    g_trace_config.software_timestamp_enabled =
        (uint8_t)(config->software_timestamp_enabled != 0u);
    g_trace_configured = 1u;
    return TRACE_GPIO_CONFIG_OK;
}

void trace_gpio_reset(void)
{
    trace_gpio_clear_config();
}

uint8_t trace_gpio_is_configured(void)
{
    return g_trace_configured;
}

#if UWB_TIMING_TRACE_ENABLE
static uint8_t trace_event_is_valid(trace_event_t event)
{
    return (uint8_t)((unsigned int)event < (unsigned int)TRACE_EVENT_COUNT);
}

static const trace_gpio_route_t *trace_gpio_route(trace_event_t event)
{
    size_t index;

    if ((g_trace_configured == 0u) ||
        (g_trace_config.gpio_enabled == 0u) ||
        (g_trace_config.write == NULL) ||
        (trace_event_is_valid(event) == 0u)) {
        return NULL;
    }

    index = (size_t)event;
    if (index >= g_trace_config.route_count) {
        return NULL;
    }
    if ((g_trace_config.routes[index].enabled == 0u) ||
        (g_trace_config.routes[index].pin == TRACE_GPIO_PIN_UNUSED)) {
        return NULL;
    }
    return &g_trace_config.routes[index];
}

static void trace_gpio_write_event(trace_event_t event, uint8_t active)
{
    const trace_gpio_route_t *route = trace_gpio_route(event);
    uint8_t level;

    if (route == NULL) {
        return;
    }

    level = (uint8_t)((active != 0u) ?
                      (route->active_high != 0u) :
                      (route->active_high == 0u));
    g_trace_config.write(g_trace_config.write_context, route->pin, level);
}

#if UWB_TIMING_TRACE_SOFTWARE_ENABLE
static void trace_software_record(trace_event_t event, trace_action_t action)
{
    if ((g_trace_configured == 0u) ||
        (g_trace_config.software_timestamp_enabled == 0u) ||
        (g_trace_config.software_probe == NULL) ||
        (trace_event_is_valid(event) == 0u)) {
        return;
    }

    (void)timing_probe_record(g_trace_config.software_probe, event, action);
}
#endif
#endif

void trace_event_set(trace_event_t event)
{
#if UWB_TIMING_TRACE_ENABLE
    trace_gpio_write_event(event, 1u);
#if UWB_TIMING_TRACE_SOFTWARE_ENABLE
    trace_software_record(event, TRACE_ACTION_SET);
#endif
#else
    (void)event;
#endif
}

void trace_event_clear(trace_event_t event)
{
#if UWB_TIMING_TRACE_ENABLE
    trace_gpio_write_event(event, 0u);
#if UWB_TIMING_TRACE_SOFTWARE_ENABLE
    trace_software_record(event, TRACE_ACTION_CLEAR);
#endif
#else
    (void)event;
#endif
}

void trace_event_pulse(trace_event_t event)
{
#if UWB_TIMING_TRACE_ENABLE
    trace_gpio_write_event(event, 1u);
#if UWB_TIMING_TRACE_SOFTWARE_ENABLE
    trace_software_record(event, TRACE_ACTION_PULSE);
#endif
    trace_gpio_write_event(event, 0u);
#else
    (void)event;
#endif
}
