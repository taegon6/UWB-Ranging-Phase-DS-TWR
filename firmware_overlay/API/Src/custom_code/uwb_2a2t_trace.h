/* Non-blocking 64-byte trace records. Board-specific GPIO/UART hooks are injected at build time. */
#ifndef UWB_2A2T_TRACE_H
#define UWB_2A2T_TRACE_H

#include <stdint.h>

#include "uwb_2a2t_config.h"

typedef enum
{
    UWB_2A2T_TRACE_BOOT = 0,
    UWB_2A2T_TRACE_SUPERFRAME_START,
    UWB_2A2T_TRACE_SLOT_START,
    UWB_2A2T_TRACE_PACKET_TX_SCHEDULED,
    UWB_2A2T_TRACE_PACKET_TX_DONE,
    UWB_2A2T_TRACE_PACKET_RX_RMARKER,
    UWB_2A2T_TRACE_PROCESS_START,
    UWB_2A2T_TRACE_PROCESS_END,
    UWB_2A2T_TRACE_TOKEN_RX,
    UWB_2A2T_TRACE_TOKEN_TIMEOUT,
    UWB_2A2T_TRACE_LATE_TX,
    UWB_2A2T_TRACE_RX_TIMEOUT,
    UWB_2A2T_TRACE_REPORT_READY,
    UWB_2A2T_TRACE_SUPERFRAME_DONE,
    UWB_2A2T_TRACE_UART_DROP
} uwb_2a2t_trace_event_t;

#if defined(__GNUC__) || defined(__clang__)
#define UWB_2A2T_PACKED __attribute__((packed))
#else
#define UWB_2A2T_PACKED
#pragma pack(push, 1)
#endif

typedef struct UWB_2A2T_PACKED
{
    uint16_t magic;
    uint8_t version;
    uint8_t node_id;
    uint8_t slot_id;
    uint8_t event_type;
    uint8_t result_code;
    uint8_t flags;
    uint32_t boot_id;
    uint32_t superframe_id;
    uint8_t sequence;
    uint8_t retry_count;
    uint16_t reserved;
    int32_t raw_distance_mm;
    int32_t corrected_distance_mm;
    uint64_t slot_start_dtu;
    uint32_t event_delta_dtu[5];
    uint32_t status_reg;
    uint16_t uart_drop_count;
    uint16_t crc16;
} uwb_2a2t_trace_record_t;

#if !defined(__GNUC__) && !defined(__clang__)
#pragma pack(pop)
#endif

typedef char uwb_2a2t_trace_record_must_be_64_bytes[
    (sizeof(uwb_2a2t_trace_record_t) == UWB_2A2T_UART_RECORD_SIZE) ? 1 : -1
];

typedef struct
{
    uwb_2a2t_trace_record_t records[UWB_2A2T_TRACE_RING_CAPACITY];
    volatile uint8_t write_index;
    volatile uint8_t read_index;
    volatile uint16_t dropped;
} uwb_2a2t_trace_ring_t;

/* The board port supplies a non-blocking UART/DMA submit callback. */
typedef uint8_t (*uwb_2a2t_uart_submit_fn)(const uint8_t *data, uint16_t length, void *context);

void uwb_2a2t_trace_init(uwb_2a2t_trace_ring_t *ring);
uint8_t uwb_2a2t_trace_enqueue(uwb_2a2t_trace_ring_t *ring, const uwb_2a2t_trace_record_t *record);
uint8_t uwb_2a2t_trace_dequeue(uwb_2a2t_trace_ring_t *ring, uwb_2a2t_trace_record_t *record);
uint8_t uwb_2a2t_trace_drain_one(uwb_2a2t_trace_ring_t *ring,
                                  uwb_2a2t_uart_submit_fn submit, void *context);

#ifndef UWB_2A2T_GPIO_SLOT_ACTIVE
#define UWB_2A2T_GPIO_SLOT_ACTIVE(level) ((void)(level))
#endif
#ifndef UWB_2A2T_GPIO_PROCESS_ACTIVE
#define UWB_2A2T_GPIO_PROCESS_ACTIVE(level) ((void)(level))
#endif
#ifndef UWB_2A2T_GPIO_REPORT_READY
#define UWB_2A2T_GPIO_REPORT_READY(level) ((void)(level))
#endif
#ifndef UWB_2A2T_GPIO_ERROR
#define UWB_2A2T_GPIO_ERROR(level) ((void)(level))
#endif

#endif /* UWB_2A2T_TRACE_H */
