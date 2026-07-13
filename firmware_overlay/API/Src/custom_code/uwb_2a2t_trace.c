#include <string.h>

#include "uwb_2a2t_trace.h"

static uint16_t crc16_ccitt(const uint8_t *data, uint32_t length)
{
    uint16_t crc = 0xFFFFU;
    uint32_t index;
    for (index = 0U; index < length; index++)
    {
        uint8_t bit;
        crc ^= (uint16_t)((uint16_t)data[index] << 8U);
        for (bit = 0U; bit < 8U; bit++)
        {
            crc = (crc & 0x8000U) ? (uint16_t)((crc << 1U) ^ 0x1021U) : (uint16_t)(crc << 1U);
        }
    }
    return crc;
}

void uwb_2a2t_trace_init(uwb_2a2t_trace_ring_t *ring)
{
    (void)memset(ring, 0, sizeof(*ring));
}

uint8_t uwb_2a2t_trace_enqueue(uwb_2a2t_trace_ring_t *ring, const uwb_2a2t_trace_record_t *record)
{
    const uint8_t next = (uint8_t)((ring->write_index + 1U) % UWB_2A2T_TRACE_RING_CAPACITY);
    if (next == ring->read_index)
    {
        ring->dropped++;
        return 0U;
    }
    ring->records[ring->write_index] = *record;
    ring->records[ring->write_index].crc16 = crc16_ccitt(
        (const uint8_t *)&ring->records[ring->write_index],
        UWB_2A2T_UART_RECORD_SIZE - sizeof(ring->records[ring->write_index].crc16));
    ring->write_index = next;
    return 1U;
}

uint8_t uwb_2a2t_trace_dequeue(uwb_2a2t_trace_ring_t *ring, uwb_2a2t_trace_record_t *record)
{
    if (ring->read_index == ring->write_index)
    {
        return 0U;
    }
    *record = ring->records[ring->read_index];
    ring->read_index = (uint8_t)((ring->read_index + 1U) % UWB_2A2T_TRACE_RING_CAPACITY);
    return 1U;
}

uint8_t uwb_2a2t_trace_drain_one(uwb_2a2t_trace_ring_t *ring,
                                  uwb_2a2t_uart_submit_fn submit, void *context)
{
    const uint8_t index = ring->read_index;
    if (index == ring->write_index || submit == 0)
    {
        return 0U;
    }
    if (submit((const uint8_t *)&ring->records[index], UWB_2A2T_UART_RECORD_SIZE, context) == 0U)
    {
        return 0U;
    }
    ring->read_index = (uint8_t)((index + 1U) % UWB_2A2T_TRACE_RING_CAPACITY);
    return 1U;
}
