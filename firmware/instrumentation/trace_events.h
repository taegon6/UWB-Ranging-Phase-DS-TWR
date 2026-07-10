#ifndef UWB_TRACE_EVENTS_H
#define UWB_TRACE_EVENTS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Stable trace-event identifiers shared by firmware, fixtures, and host tools.
 * Values 0 through 20 are the required pre-hardware contract.  New events must
 * be appended so that previously captured software records remain decodable.
 */
typedef enum {
    TRACE_IRQ_ASSERT = 0,
    TRACE_ISR_ENTRY = 1,
    TRACE_ISR_EXIT = 2,
    TRACE_SPI_STATUS_START = 3,
    TRACE_SPI_STATUS_END = 4,
    TRACE_SPI_FRAME_START = 5,
    TRACE_SPI_FRAME_END = 6,
    TRACE_SPI_CIR_START = 7,
    TRACE_SPI_CIR_END = 8,
    TRACE_UART_ENQUEUE_START = 9,
    TRACE_UART_ENQUEUE_END = 10,
    TRACE_UART_TX_START = 11,
    TRACE_UART_TX_END = 12,
    TRACE_CIR_READ_START = 13,
    TRACE_CIR_READ_END = 14,
    TRACE_PHASE_START = 15,
    TRACE_PHASE_END = 16,
    TRACE_FILTER_START = 17,
    TRACE_FILTER_END = 18,
    TRACE_FRAME_START = 19,
    TRACE_FRAME_END = 20,

    /* Additional markers required by the wider instrumentation specification. */
    TRACE_RX_EVENT = 21,
    TRACE_TX_PREP_START = 22,
    TRACE_TX_ARMED = 23,
    TRACE_LOG_START = 24,
    TRACE_LOG_END = 25,
    TRACE_ERROR_PULSE = 26,
    TRACE_SPI_TIMESTAMP_START = 27,
    TRACE_SPI_TIMESTAMP_END = 28,
    TRACE_SPI_CONFIG_START = 29,
    TRACE_SPI_CONFIG_END = 30,
    TRACE_UART_ENCODE_START = 31,
    TRACE_UART_ENCODE_END = 32,
    TRACE_UART_API_START = 33,
    TRACE_UART_API_END = 34,
    TRACE_CIR_DECODE_START = 35,
    TRACE_CIR_DECODE_END = 36,
    TRACE_PHASE_EXTRACT_START = 37,
    TRACE_PHASE_EXTRACT_END = 38,
    TRACE_PHASE_COMBINE_START = 39,
    TRACE_PHASE_COMBINE_END = 40,
    TRACE_RESULT_PACKAGE_START = 41,
    TRACE_RESULT_PACKAGE_END = 42,
    TRACE_UART_HOST_ARRIVAL = 43,

    TRACE_EVENT_COUNT = 44,
    TRACE_EVENT_INVALID = 255
} trace_event_t;

/* Action stored by the optional software-timestamp probe. */
typedef enum {
    TRACE_ACTION_CLEAR = 0,
    TRACE_ACTION_SET = 1,
    TRACE_ACTION_PULSE = 2
} trace_action_t;

#define UWB_TRACE_REQUIRED_EVENT_COUNT ((uint16_t)21u)

#ifdef __cplusplus
}
#endif

#endif /* UWB_TRACE_EVENTS_H */
