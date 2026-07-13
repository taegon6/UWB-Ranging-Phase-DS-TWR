/* Direct 2-anchor/2-tag initiator. Derived from ds_twr_initiator_final.c. */
#include <deca_device_api.h>
#include <deca_regs.h>
#include <deca_spi.h>
#include <port.h>
#include <string.h>
#include <shared_defines.h>
#include <shared_functions.h>
#include <example_selection.h>

#include "uwb_2a2t_config.h"
#include "uwb_2a2t_build_identity.h"
#include "uwb_2a2t_protocol.h"
#include "uwb_2a2t_trace.h"

#if defined(DS_TWR_2A2T_TAG)

extern void test_run_info(unsigned char *data);
extern dwt_txconfig_t txconfig_options_ch9;

#if defined(UWB_NODE_T1)
static const uint8_t local_tag[2] = {'T', '1'};
static const unsigned char boot_message[] = UWB_2A2T_FWID;
#elif defined(UWB_NODE_T2)
static const uint8_t local_tag[2] = {'T', '2'};
static const unsigned char boot_message[] = UWB_2A2T_FWID;
#else
#error "DS_TWR_2A2T_TAG requires UWB_NODE_T1 or UWB_NODE_T2"
#endif

#define UWB_2A2T_RX_BUFFER_LENGTH 40U

static dwt_config_t uwb_2a2t_radio_config = {
    9, DWT_PLEN_128, DWT_PAC8, 9, 9, 1, DWT_BR_6M8, DWT_PHRMODE_STD,
    DWT_PHRRATE_STD, (128 + 1 + 8 - 8), DWT_STS_MODE_OFF, DWT_STS_LEN_64, DWT_PDOA_M0
};

static uint8_t tx_poll[UWB_2A2T_POLL_DATA_LENGTH] =
    {0x41, 0x88, 0, 0xCA, 0xDE, 'A', '1', 'T', '1', UWB_2A2T_POLL_FUNCTION};
static uint8_t rx_response[UWB_2A2T_RESPONSE_DATA_LENGTH] =
    {0x41, 0x88, 0, 0xCA, 0xDE, 'T', '1', 'A', '1', UWB_2A2T_RESPONSE_FUNCTION, 0x02};
static uint8_t tx_final[UWB_2A2T_FINAL_DATA_LENGTH] =
    {0x41, 0x88, 0, 0xCA, 0xDE, 'A', '1', 'T', '1', UWB_2A2T_FINAL_FUNCTION};
static uint8_t tx_post_final[UWB_2A2T_POST_FINAL_DATA_LENGTH] =
    {0x41, 0x88, 0, 0xCA, 0xDE, 'A', '1', 'T', '1', UWB_2A2T_POST_FINAL_FUNCTION};
static uint8_t rx_report[UWB_2A2T_REPORT_DATA_LENGTH] =
    {0x41, 0x88, 0, 0xCA, 0xDE, 'T', '1', 'A', '1', UWB_2A2T_REPORT_FUNCTION, 0, 0, 0, 0};
static uint8_t rx_buffer[UWB_2A2T_RX_BUFFER_LENGTH];
static uwb_2a2t_trace_ring_t trace_ring;
static uint32_t superframe_id;
static uint32_t status_reg;

static void write_timestamp(uint8_t *field, uint64_t timestamp)
{
    uint8_t index;
    for (index = 0U; index < 4U; index++)
    {
        field[index] = (uint8_t)timestamp;
        timestamp >>= 8U;
    }
}

static int32_t report_distance_mm(const uint8_t *field)
{
    return (int32_t)((uint32_t)field[0] | ((uint32_t)field[1] << 8U) |
                     ((uint32_t)field[2] << 16U) | ((uint32_t)field[3] << 24U));
}

static void trace_event(uwb_2a2t_trace_event_t event, const uwb_2a2t_link_t *link,
                        uint8_t result, uint64_t timestamp)
{
    uwb_2a2t_trace_record_t record;
    (void)memset(&record, 0, sizeof(record));
    record.magic = 0x3255U;
    record.version = UWB_2A2T_PROTOCOL_VERSION;
#if defined(UWB_NODE_T1)
    record.node_id = 3U;
#else
    record.node_id = 4U;
#endif
    record.slot_id = link->slot_id;
    record.event_type = (uint8_t)event;
    record.result_code = result;
    record.superframe_id = superframe_id;
    record.sequence = link->sequence;
    record.slot_start_dtu = timestamp;
    record.uart_drop_count = trace_ring.dropped;
    (void)uwb_2a2t_trace_enqueue(&trace_ring, &record);
}

static void set_link_frames(const uwb_2a2t_link_t *link)
{
    uwb_2a2t_set_header(tx_poll, link->anchor, link->tag, UWB_2A2T_POLL_FUNCTION, link->sequence);
    uwb_2a2t_set_header(rx_response, link->tag, link->anchor, UWB_2A2T_RESPONSE_FUNCTION, link->sequence);
    uwb_2a2t_set_header(tx_final, link->anchor, link->tag, UWB_2A2T_FINAL_FUNCTION, link->sequence);
    uwb_2a2t_set_header(tx_post_final, link->anchor, link->tag, UWB_2A2T_POST_FINAL_FUNCTION, link->sequence);
    uwb_2a2t_set_header(rx_report, link->tag, link->anchor, UWB_2A2T_REPORT_FUNCTION, link->sequence);
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

static uint8_t start_poll(const uwb_2a2t_link_t *link, uint64_t reference_timestamp, uint8_t delayed)
{
    int start_result;
    dwt_writetxdata(UWB_2A2T_POLL_DATA_LENGTH, tx_poll, 0U);
    dwt_writetxfctrl(UWB_2A2T_POLL_PSDU_LENGTH, 0U, 1U);
    if (delayed != 0U)
    {
        const uint32_t start_time = (uint32_t)((reference_timestamp +
            ((uint64_t)UWB_2A2T_BOOTSTRAP_GUARD_UUS * UUS_TO_DWT_TIME)) >> 8U);
        dwt_setdelayedtrxtime(start_time);
        start_result = dwt_starttx(DWT_START_TX_DELAYED | DWT_RESPONSE_EXPECTED);
    }
    else
    {
        start_result = dwt_starttx(DWT_START_TX_IMMEDIATE | DWT_RESPONSE_EXPECTED);
    }
    if (start_result != DWT_SUCCESS)
    {
        trace_event(UWB_2A2T_TRACE_LATE_TX, link, 1U, reference_timestamp);
        return 0U;
    }
    trace_event(UWB_2A2T_TRACE_PACKET_TX_SCHEDULED, link, 0U, reference_timestamp);
    return 1U;
}

static uint8_t run_local_link(const uwb_2a2t_link_t *link, uint64_t start_reference,
                              uint8_t delayed_start, uint64_t *report_rx_timestamp)
{
    uint64_t poll_tx_timestamp;
    uint64_t response_rx_timestamp;
    uint64_t final_tx_timestamp;
    uint32_t delayed_tx_time;
    int start_result;

    set_link_frames(link);
    UWB_2A2T_GPIO_SLOT_ACTIVE(1U);
    if (link->slot_id == UWB_2A2T_SLOT_A1_T1)
    {
        trace_event(UWB_2A2T_TRACE_SUPERFRAME_START, link, 0U, start_reference);
    }
    trace_event(UWB_2A2T_TRACE_SLOT_START, link, 0U, start_reference);
    dwt_setrxaftertxdelay(UWB_2A2T_POLL_TX_TO_RESP_RX_DELAY_UUS);
    dwt_setrxtimeout(UWB_2A2T_RESPONSE_RX_TIMEOUT_UUS);
    dwt_setpreambledetecttimeout(UWB_2A2T_PREAMBLE_TIMEOUT_PAC);
    if (start_poll(link, start_reference, delayed_start) == 0U)
    {
        UWB_2A2T_GPIO_ERROR(1U);
        UWB_2A2T_GPIO_SLOT_ACTIVE(0U);
        return 0U;
    }
    if (wait_for_rx() == 0U ||
        read_expected_frame(UWB_2A2T_RESPONSE_PSDU_LENGTH, link->tag, link->anchor,
                            UWB_2A2T_RESPONSE_FUNCTION, link->sequence) == 0U)
    {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR);
        trace_event(UWB_2A2T_TRACE_RX_TIMEOUT, link, 2U, 0U);
        UWB_2A2T_GPIO_SLOT_ACTIVE(0U);
        return 0U;
    }
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_TXFRS_BIT_MASK);
    poll_tx_timestamp = get_tx_timestamp_u64();
    response_rx_timestamp = get_rx_timestamp_u64();
    trace_event(UWB_2A2T_TRACE_PACKET_RX_RMARKER, link, 0U, response_rx_timestamp);

    delayed_tx_time = (uint32_t)((response_rx_timestamp +
        ((uint64_t)UWB_2A2T_RESP_RX_TO_FINAL_TX_DELAY_UUS * UUS_TO_DWT_TIME)) >> 8U);
    dwt_setdelayedtrxtime(delayed_tx_time);
    final_tx_timestamp = (((uint64_t)(delayed_tx_time & 0xFFFFFFFEUL)) << 8U) + 16385U;
    write_timestamp(&tx_final[UWB_2A2T_FINAL_POLL_TX_TS_INDEX], poll_tx_timestamp);
    write_timestamp(&tx_final[UWB_2A2T_FINAL_RESP_RX_TS_INDEX], response_rx_timestamp);
    write_timestamp(&tx_final[UWB_2A2T_FINAL_TX_TS_INDEX], final_tx_timestamp);
    (void)memset(&tx_final[UWB_2A2T_FINAL_PHASE_INDEX], 0,
                 UWB_2A2T_FINAL_DATA_LENGTH - UWB_2A2T_FINAL_PHASE_INDEX);
    uwb_2a2t_set_final_extension(tx_final, link->slot_id, superframe_id);
    dwt_writetxdata(UWB_2A2T_FINAL_DATA_LENGTH, tx_final, 0U);
    dwt_writetxfctrl(UWB_2A2T_FINAL_PSDU_LENGTH, 0U, 1U);
    if (dwt_starttx(DWT_START_TX_DELAYED) != DWT_SUCCESS)
    {
        trace_event(UWB_2A2T_TRACE_LATE_TX, link, 3U, response_rx_timestamp);
        UWB_2A2T_GPIO_SLOT_ACTIVE(0U);
        return 0U;
    }
    while ((dwt_read32bitreg(SYS_STATUS_ID) & SYS_STATUS_TXFRS_BIT_MASK) == 0U)
    {
    }
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);

    delayed_tx_time = (uint32_t)((final_tx_timestamp +
        ((uint64_t)UWB_2A2T_FINAL_TX_TO_POST_FINAL_DELAY_UUS * UUS_TO_DWT_TIME)) >> 8U);
    dwt_setdelayedtrxtime(delayed_tx_time);
    dwt_writetxdata(UWB_2A2T_POST_FINAL_DATA_LENGTH, tx_post_final, 0U);
    dwt_writetxfctrl(UWB_2A2T_POST_FINAL_PSDU_LENGTH, 0U, 1U);
    if (dwt_starttx(DWT_START_TX_DELAYED) != DWT_SUCCESS)
    {
        trace_event(UWB_2A2T_TRACE_LATE_TX, link, 4U, final_tx_timestamp);
        UWB_2A2T_GPIO_SLOT_ACTIVE(0U);
        return 0U;
    }
    while ((dwt_read32bitreg(SYS_STATUS_ID) & SYS_STATUS_TXFRS_BIT_MASK) == 0U)
    {
    }
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);

    dwt_setrxtimeout(UWB_2A2T_REPORT_RX_TIMEOUT_UUS);
    dwt_setpreambledetecttimeout(0U);
    if (dwt_rxenable(DWT_START_RX_IMMEDIATE) != DWT_SUCCESS || wait_for_rx() == 0U ||
        read_expected_frame(UWB_2A2T_REPORT_PSDU_LENGTH, link->tag, link->anchor,
                            UWB_2A2T_REPORT_FUNCTION, link->sequence) == 0U)
    {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR);
        trace_event(UWB_2A2T_TRACE_RX_TIMEOUT, link, 5U, 0U);
        UWB_2A2T_GPIO_SLOT_ACTIVE(0U);
        return 0U;
    }
    *report_rx_timestamp = get_rx_timestamp_u64();
    (void)report_distance_mm(&rx_buffer[UWB_2A2T_REPORT_DISTANCE_INDEX]);
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
    trace_event(UWB_2A2T_TRACE_REPORT_READY, link, 0U, *report_rx_timestamp);
    UWB_2A2T_GPIO_SLOT_ACTIVE(0U);
    return 1U;
}

static uint8_t wait_for_other_tag_token(uint8_t expected_sequence, uint64_t *token_timestamp)
{
    uwb_2a2t_link_t expected;
    uwb_2a2t_link_for_sequence(expected_sequence, &expected);
    dwt_setrxtimeout(UWB_2A2T_TOKEN_RX_TIMEOUT_UUS);
    dwt_setpreambledetecttimeout(0U);
    if (dwt_rxenable(DWT_START_RX_IMMEDIATE) != DWT_SUCCESS || wait_for_rx() == 0U ||
        read_expected_frame(UWB_2A2T_REPORT_PSDU_LENGTH, expected.tag, expected.anchor,
                            UWB_2A2T_REPORT_FUNCTION, expected.sequence) == 0U)
    {
        dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_TO | SYS_STATUS_ALL_RX_ERR);
        trace_event(UWB_2A2T_TRACE_TOKEN_TIMEOUT, &expected, 1U, 0U);
        return 0U;
    }
    *token_timestamp = get_rx_timestamp_u64();
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
    trace_event(UWB_2A2T_TRACE_TOKEN_RX, &expected, 0U, *token_timestamp);
    return 1U;
}

int ds_twr_2a2t_tag(void)
{
    uint8_t sequence;
    uint8_t token_sequence;
    uint8_t wait_for_token;
    uint64_t start_reference = 0U;
    uint64_t report_rx_timestamp;

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

#if defined(UWB_NODE_T1)
    sequence = 0U;
    token_sequence = 0U;
    wait_for_token = 0U;
#else
    sequence = 2U;
    token_sequence = 1U;
    wait_for_token = 1U;
#endif
    {
        uwb_2a2t_link_t boot_link;
        uwb_2a2t_link_for_sequence(sequence, &boot_link);
        trace_event(UWB_2A2T_TRACE_BOOT, &boot_link, 0U, 0U);
    }
    for (;;)
    {
        uwb_2a2t_link_t link;
        if (wait_for_token != 0U)
        {
            if (wait_for_other_tag_token(token_sequence, &start_reference) == 0U)
            {
                continue; /* Fail closed: no unscheduled Poll after token loss. */
            }
            sequence = (uint8_t)((token_sequence + 1U) & 0xFFU);
            if ((token_sequence & 0x03U) == UWB_2A2T_SLOT_A2_T2)
            {
                superframe_id++;
            }
            wait_for_token = 0U;
        }
        uwb_2a2t_link_for_sequence(sequence, &link);
        if (!uwb_2a2t_addresses_equal(link.tag, local_tag) ||
            run_local_link(&link, start_reference, (uint8_t)(start_reference != 0U), &report_rx_timestamp) == 0U)
        {
            trace_event(UWB_2A2T_TRACE_LATE_TX, &link, 6U, start_reference);
            token_sequence = sequence;
            wait_for_token = 1U; /* No retry TX; wait only for an explicitly valid token. */
            continue;
        }
        start_reference = report_rx_timestamp;
        if (link.slot_id == UWB_2A2T_SLOT_A1_T1 || link.slot_id == UWB_2A2T_SLOT_A1_T2)
        {
            sequence = (uint8_t)((sequence + 1U) & 0xFFU);
        }
        else
        {
            if (link.slot_id == UWB_2A2T_SLOT_A2_T2)
            {
                superframe_id++;
                trace_event(UWB_2A2T_TRACE_SUPERFRAME_DONE, &link, 0U, report_rx_timestamp);
            }
            token_sequence = (uint8_t)((sequence + 2U) & 0xFFU);
            wait_for_token = 1U;
        }
    }
}

#endif /* DS_TWR_2A2T_TAG */
