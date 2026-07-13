/* Direct 2-anchor/2-tag responder. Derived from ds_twr_responder_final.c. */
#include <deca_device_api.h>
#include <deca_regs.h>
#include <deca_spi.h>
#include <port.h>
#include <string.h>
#include <shared_defines.h>
#include <shared_functions.h>
#include <example_selection.h>

#include "uwb_2a2t_config.h"
#include "uwb_2a2t_protocol.h"
#include "uwb_2a2t_trace.h"

#if defined(DS_TWR_2A2T_ANCHOR)

extern void test_run_info(unsigned char *data);
extern dwt_txconfig_t txconfig_options_ch9;

#if defined(UWB_NODE_A1)
static const uint8_t local_anchor[2] = {'A', '1'};
static const unsigned char boot_message[] = "FWID:A1 2A2T";
#elif defined(UWB_NODE_A2)
static const uint8_t local_anchor[2] = {'A', '2'};
static const unsigned char boot_message[] = "FWID:A2 2A2T";
#else
#error "DS_TWR_2A2T_ANCHOR requires UWB_NODE_A1 or UWB_NODE_A2"
#endif

#define UWB_2A2T_RX_BUFFER_LENGTH 40U
#define UWB_2A2T_SPEED_OF_LIGHT 299702547.0

static dwt_config_t uwb_2a2t_radio_config = {
    9, DWT_PLEN_128, DWT_PAC8, 9, 9, 1, DWT_BR_6M8, DWT_PHRMODE_STD,
    DWT_PHRRATE_STD, (128 + 1 + 8 - 8), DWT_STS_MODE_OFF, DWT_STS_LEN_64, DWT_PDOA_M0
};
static uint8_t rx_poll[UWB_2A2T_POLL_DATA_LENGTH] =
    {0x41, 0x88, 0, 0xCA, 0xDE, 'A', '1', 'T', '1', UWB_2A2T_POLL_FUNCTION};
static uint8_t tx_response[UWB_2A2T_RESPONSE_DATA_LENGTH] =
    {0x41, 0x88, 0, 0xCA, 0xDE, 'T', '1', 'A', '1', UWB_2A2T_RESPONSE_FUNCTION, 0x02};
static uint8_t rx_final[UWB_2A2T_FINAL_DATA_LENGTH] =
    {0x41, 0x88, 0, 0xCA, 0xDE, 'A', '1', 'T', '1', UWB_2A2T_FINAL_FUNCTION};
static uint8_t rx_post_final[UWB_2A2T_POST_FINAL_DATA_LENGTH] =
    {0x41, 0x88, 0, 0xCA, 0xDE, 'A', '1', 'T', '1', UWB_2A2T_POST_FINAL_FUNCTION};
static uint8_t tx_report[UWB_2A2T_REPORT_DATA_LENGTH] =
    {0x41, 0x88, 0, 0xCA, 0xDE, 'T', '1', 'A', '1', UWB_2A2T_REPORT_FUNCTION, 0, 0, 0, 0};
static uint8_t rx_buffer[UWB_2A2T_RX_BUFFER_LENGTH];
static uint32_t status_reg;
static uwb_2a2t_trace_ring_t trace_ring;

static uint64_t read_timestamp(const uint8_t *field)
{
    uint64_t value = 0U;
    uint8_t index;
    for (index = 0U; index < 4U; index++)
    {
        value |= ((uint64_t)field[index] << (8U * index));
    }
    return value;
}

static void write_distance(uint8_t *field, int32_t distance_mm)
{
    field[0] = (uint8_t)distance_mm;
    field[1] = (uint8_t)(distance_mm >> 8U);
    field[2] = (uint8_t)(distance_mm >> 16U);
    field[3] = (uint8_t)(distance_mm >> 24U);
}

static void set_link_frames(const uwb_2a2t_link_t *link)
{
    uwb_2a2t_set_header(rx_poll, link->anchor, link->tag, UWB_2A2T_POLL_FUNCTION, link->sequence);
    uwb_2a2t_set_header(tx_response, link->tag, link->anchor, UWB_2A2T_RESPONSE_FUNCTION, link->sequence);
    uwb_2a2t_set_header(rx_final, link->anchor, link->tag, UWB_2A2T_FINAL_FUNCTION, link->sequence);
    uwb_2a2t_set_header(rx_post_final, link->anchor, link->tag, UWB_2A2T_POST_FINAL_FUNCTION, link->sequence);
    uwb_2a2t_set_header(tx_report, link->tag, link->anchor, UWB_2A2T_REPORT_FUNCTION, link->sequence);
}

static uint8_t wait_for_rx(void)
{
    while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) &
             (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR)))
    {
    }
    return (uint8_t)((status_reg & SYS_STATUS_RXFCG_BIT_MASK) != 0U);
}

static uint8_t read_expected_frame(uint32_t required_length, const uint8_t *destination,
                                   const uint8_t *source, uint8_t function, uint8_t sequence)
{
    const uint32_t frame_len = dwt_read32bitreg(RX_FINFO_ID) & FRAME_LEN_MAX_EX;
    if (frame_len < required_length || frame_len > UWB_2A2T_RX_BUFFER_LENGTH)
    {
        return 0U;
    }
    dwt_readrxdata(rx_buffer, frame_len, 0U);
    return uwb_2a2t_header_matches(rx_buffer, destination, source, function, sequence);
}

static void trace_event(uwb_2a2t_trace_event_t event, const uwb_2a2t_link_t *link,
                        uint8_t result, uint64_t timestamp)
{
    uwb_2a2t_trace_record_t record;
    (void)memset(&record, 0, sizeof(record));
    record.magic = 0x3255U;
    record.version = UWB_2A2T_PROTOCOL_VERSION;
#if defined(UWB_NODE_A1)
    record.node_id = 1U;
#else
    record.node_id = 2U;
#endif
    record.slot_id = link->slot_id;
    record.event_type = (uint8_t)event;
    record.result_code = result;
    record.sequence = link->sequence;
    record.slot_start_dtu = timestamp;
    record.uart_drop_count = trace_ring.dropped;
    (void)uwb_2a2t_trace_enqueue(&trace_ring, &record);
}

static uint8_t run_bound_link(const uwb_2a2t_link_t *link, uint64_t poll_rx_timestamp)
{
    uint32_t response_tx_time;
    uint32_t report_tx_time;
    uint64_t response_tx_timestamp;
    uint64_t final_rx_timestamp;
    uint64_t post_final_rx_timestamp;
    double round1, reply1, round2, reply2, denominator, tof_dtu;
    int32_t distance_mm;

    set_link_frames(link);
    UWB_2A2T_GPIO_PROCESS_ACTIVE(1U);
    response_tx_time = (uint32_t)((poll_rx_timestamp +
        ((uint64_t)UWB_2A2T_POLL_RX_TO_RESP_TX_DELAY_UUS * UUS_TO_DWT_TIME)) >> 8U);
    dwt_setdelayedtrxtime(response_tx_time);
    dwt_writetxdata(UWB_2A2T_RESPONSE_DATA_LENGTH, tx_response, 0U);
    dwt_writetxfctrl(UWB_2A2T_RESPONSE_PSDU_LENGTH, 0U, 1U);
    dwt_setrxaftertxdelay(UWB_2A2T_RESP_TX_TO_FINAL_RX_DELAY_UUS);
    dwt_setrxtimeout(UWB_2A2T_FINAL_RX_TIMEOUT_UUS);
    dwt_setpreambledetecttimeout(UWB_2A2T_PREAMBLE_TIMEOUT_PAC);
    if (dwt_starttx(DWT_START_TX_DELAYED | DWT_RESPONSE_EXPECTED) != DWT_SUCCESS)
    {
        trace_event(UWB_2A2T_TRACE_LATE_TX, link, 1U, poll_rx_timestamp);
        UWB_2A2T_GPIO_PROCESS_ACTIVE(0U);
        return 0U;
    }
    while ((dwt_read32bitreg(SYS_STATUS_ID) & SYS_STATUS_TXFRS_BIT_MASK) == 0U)
    {
    }
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);
    response_tx_timestamp = get_tx_timestamp_u64();
    if (wait_for_rx() == 0U ||
        read_expected_frame(UWB_2A2T_FINAL_PSDU_LENGTH, link->anchor, link->tag,
                            UWB_2A2T_FINAL_FUNCTION, link->sequence) == 0U ||
        uwb_2a2t_final_extension_matches(rx_buffer, link->slot_id) == 0U)
    {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR);
        trace_event(UWB_2A2T_TRACE_RX_TIMEOUT, link, 2U, 0U);
        UWB_2A2T_GPIO_PROCESS_ACTIVE(0U);
        return 0U;
    }
    final_rx_timestamp = get_rx_timestamp_u64();
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
    dwt_setdelayedtrxtime((uint32_t)((final_rx_timestamp +
        ((uint64_t)UWB_2A2T_FINAL_RX_TO_POST_FINAL_RX_DELAY_UUS * UUS_TO_DWT_TIME)) >> 8U));
    dwt_setrxtimeout(UWB_2A2T_POST_FINAL_RX_TIMEOUT_UUS);
    dwt_setpreambledetecttimeout(0U);
    if (dwt_rxenable(DWT_START_RX_DELAYED) != DWT_SUCCESS || wait_for_rx() == 0U ||
        read_expected_frame(UWB_2A2T_POST_FINAL_PSDU_LENGTH, link->anchor, link->tag,
                            UWB_2A2T_POST_FINAL_FUNCTION, link->sequence) == 0U)
    {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR);
        trace_event(UWB_2A2T_TRACE_RX_TIMEOUT, link, 3U, 0U);
        UWB_2A2T_GPIO_PROCESS_ACTIVE(0U);
        return 0U;
    }
    post_final_rx_timestamp = get_rx_timestamp_u64();
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);

    round1 = (double)(read_timestamp(&rx_buffer[UWB_2A2T_FINAL_RESP_RX_TS_INDEX]) -
                      read_timestamp(&rx_buffer[UWB_2A2T_FINAL_POLL_TX_TS_INDEX]));
    reply1 = (double)(read_timestamp(&rx_buffer[UWB_2A2T_FINAL_TX_TS_INDEX]) -
                      read_timestamp(&rx_buffer[UWB_2A2T_FINAL_RESP_RX_TS_INDEX]));
    round2 = (double)(final_rx_timestamp - response_tx_timestamp);
    reply2 = (double)(response_tx_timestamp - poll_rx_timestamp);
    denominator = round1 + round2 + reply1 + reply2;
    tof_dtu = (denominator == 0.0) ? 0.0 : ((round1 * round2) - (reply1 * reply2)) / denominator;
    distance_mm = (int32_t)(tof_dtu * DWT_TIME_UNITS * UWB_2A2T_SPEED_OF_LIGHT * 1000.0);

    report_tx_time = (uint32_t)((post_final_rx_timestamp +
        ((uint64_t)UWB_2A2T_POST_FINAL_RX_TO_REPORT_DELAY_UUS * UUS_TO_DWT_TIME)) >> 8U);
    dwt_setdelayedtrxtime(report_tx_time);
    write_distance(&tx_report[UWB_2A2T_REPORT_DISTANCE_INDEX], distance_mm);
    dwt_writetxdata(UWB_2A2T_REPORT_DATA_LENGTH, tx_report, 0U);
    dwt_writetxfctrl(UWB_2A2T_REPORT_PSDU_LENGTH, 0U, 0U);
    UWB_2A2T_GPIO_REPORT_READY(1U);
    if (dwt_starttx(DWT_START_TX_DELAYED) != DWT_SUCCESS)
    {
        trace_event(UWB_2A2T_TRACE_LATE_TX, link, 4U, post_final_rx_timestamp);
        UWB_2A2T_GPIO_REPORT_READY(0U);
        UWB_2A2T_GPIO_PROCESS_ACTIVE(0U);
        return 0U;
    }
    while ((dwt_read32bitreg(SYS_STATUS_ID) & SYS_STATUS_TXFRS_BIT_MASK) == 0U)
    {
    }
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);
    trace_event(UWB_2A2T_TRACE_REPORT_READY, link, 0U, post_final_rx_timestamp);
    UWB_2A2T_GPIO_REPORT_READY(0U);
    UWB_2A2T_GPIO_PROCESS_ACTIVE(0U);
    return 1U;
}

int ds_twr_2a2t_anchor(void)
{
    test_run_info((unsigned char *)boot_message);
    port_set_dw_ic_spi_fastrate();
    reset_DWIC();
    while (!dwt_checkidlerc())
    {
    }
    if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR || dwt_configure(&uwb_2a2t_radio_config) != DWT_SUCCESS)
    {
        test_run_info((unsigned char *)"2A2T CFG FAIL");
        while (1)
        {
        }
    }
    dwt_configuretxrf(&txconfig_options_ch9);
    dwt_setrxantennadelay(16385U);
    dwt_settxantennadelay(16385U);
    dwt_setlnapamode(DWT_LNA_ENABLE | DWT_PA_ENABLE);
    dwt_configciadiag(UWB_2A2T_CIR_PHASE_ENABLE);
    uwb_2a2t_trace_init(&trace_ring);
    {
        uwb_2a2t_link_t boot_link;
#if defined(UWB_NODE_A1)
        uwb_2a2t_link_for_sequence(0U, &boot_link);
#else
        uwb_2a2t_link_for_sequence(1U, &boot_link);
#endif
        trace_event(UWB_2A2T_TRACE_BOOT, &boot_link, 0U, 0U);
    }
    for (;;)
    {
        uint32_t frame_len;
        uint8_t sequence;
        uwb_2a2t_link_t link;
        dwt_setrxtimeout(0U);
        dwt_setpreambledetecttimeout(0U);
        if (dwt_rxenable(DWT_START_RX_IMMEDIATE) != DWT_SUCCESS || wait_for_rx() == 0U)
        {
            dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR);
            continue;
        }
        frame_len = dwt_read32bitreg(RX_FINFO_ID) & FRAME_LEN_MAX_EX;
        if (frame_len < UWB_2A2T_POLL_PSDU_LENGTH || frame_len > UWB_2A2T_RX_BUFFER_LENGTH)
        {
            dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_ERR);
            continue;
        }
        dwt_readrxdata(rx_buffer, frame_len, 0U);
        sequence = rx_buffer[UWB_2A2T_SEQUENCE_INDEX];
        uwb_2a2t_link_for_sequence(sequence, &link);
        if (!uwb_2a2t_addresses_equal(link.anchor, local_anchor) ||
            uwb_2a2t_header_matches(rx_buffer, link.anchor, link.tag,
                                    UWB_2A2T_POLL_FUNCTION, sequence) == 0U)
        {
            dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
            continue;
        }
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
        trace_event(UWB_2A2T_TRACE_PACKET_RX_RMARKER, &link, 0U, get_rx_timestamp_u64());
        (void)run_bound_link(&link, get_rx_timestamp_u64());
    }
}

#endif /* DS_TWR_2A2T_ANCHOR */
