/* Phase 6 direct-2A2T wire contract.  Baseline sources remain unchanged. */
#ifndef UWB_2A2T_PROTOCOL_H
#define UWB_2A2T_PROTOCOL_H

#include <stdint.h>

#define UWB_2A2T_FCS_LENGTH                    2U
#define UWB_2A2T_MAC_HEADER_LENGTH             10U
#define UWB_2A2T_SEQUENCE_INDEX                2U
#define UWB_2A2T_DESTINATION_INDEX             5U
#define UWB_2A2T_SOURCE_INDEX                  7U
#define UWB_2A2T_FUNCTION_INDEX                9U

#define UWB_2A2T_POLL_FUNCTION                 0x21U
#define UWB_2A2T_RESPONSE_FUNCTION             0x10U
#define UWB_2A2T_FINAL_FUNCTION                0x23U
#define UWB_2A2T_POST_FINAL_FUNCTION           0x12U
#define UWB_2A2T_REPORT_FUNCTION               0x31U

/* dwt_writetxdata length excludes the hardware-appended FCS. */
#define UWB_2A2T_POLL_DATA_LENGTH              10U
#define UWB_2A2T_RESPONSE_DATA_LENGTH          11U
#define UWB_2A2T_FINAL_DATA_LENGTH             32U
#define UWB_2A2T_POST_FINAL_DATA_LENGTH        10U
#define UWB_2A2T_REPORT_DATA_LENGTH            14U

/* dwt_writetxfctrl programmed lengths include FCS. */
#define UWB_2A2T_POLL_PSDU_LENGTH              12U
#define UWB_2A2T_RESPONSE_PSDU_LENGTH          13U
#define UWB_2A2T_FINAL_PSDU_LENGTH             34U
#define UWB_2A2T_POST_FINAL_PSDU_LENGTH        12U
#define UWB_2A2T_REPORT_PSDU_LENGTH            16U

#define UWB_2A2T_FINAL_POLL_TX_TS_INDEX        10U
#define UWB_2A2T_FINAL_RESP_RX_TS_INDEX        14U
#define UWB_2A2T_FINAL_TX_TS_INDEX             18U
#define UWB_2A2T_FINAL_PHASE_INDEX             22U
#define UWB_2A2T_FINAL_EXTENSION_INDEX         26U
#define UWB_2A2T_FINAL_EXTENSION_LENGTH        6U
#define UWB_2A2T_REPORT_DISTANCE_INDEX         10U
#define UWB_2A2T_PROTOCOL_VERSION              1U

#define UWB_2A2T_SLOT_COUNT                    4U

#if (defined(UWB_NODE_A1) + defined(UWB_NODE_A2) + defined(UWB_NODE_T1) + defined(UWB_NODE_T2)) != 1
#error "Define exactly one of UWB_NODE_A1/UWB_NODE_A2/UWB_NODE_T1/UWB_NODE_T2"
#endif

#if (defined(UWB_2A2T_COORDINATOR) + defined(UWB_2A2T_FOLLOWER)) > 1
#error "A tag cannot be both coordinator and follower"
#endif

typedef enum
{
    UWB_2A2T_SLOT_A1_T1 = 0,
    UWB_2A2T_SLOT_A2_T1 = 1,
    UWB_2A2T_SLOT_A1_T2 = 2,
    UWB_2A2T_SLOT_A2_T2 = 3
} uwb_2a2t_slot_t;

typedef struct
{
    uint8_t slot_id;
    uint8_t sequence;
    uint8_t superframe_mod64;
    uint8_t anchor[2];
    uint8_t tag[2];
} uwb_2a2t_link_t;

static inline void uwb_2a2t_link_for_sequence(uint8_t sequence, uwb_2a2t_link_t *link)
{
    const uint8_t slot = (uint8_t)(sequence & 0x03U);
    link->slot_id = slot;
    link->sequence = sequence;
    link->superframe_mod64 = (uint8_t)(sequence >> 2U);
    link->anchor[0] = (slot == UWB_2A2T_SLOT_A1_T1 || slot == UWB_2A2T_SLOT_A1_T2) ? 'A' : 'A';
    link->anchor[1] = (slot == UWB_2A2T_SLOT_A1_T1 || slot == UWB_2A2T_SLOT_A1_T2) ? '1' : '2';
    link->tag[0] = 'T';
    link->tag[1] = (slot == UWB_2A2T_SLOT_A1_T1 || slot == UWB_2A2T_SLOT_A2_T1) ? '1' : '2';
}

static inline uint8_t uwb_2a2t_addresses_equal(const uint8_t *left, const uint8_t *right)
{
    return (uint8_t)((left[0] == right[0]) && (left[1] == right[1]));
}

static inline void uwb_2a2t_set_header(uint8_t *frame, const uint8_t *destination,
                                        const uint8_t *source, uint8_t function, uint8_t sequence)
{
    frame[UWB_2A2T_SEQUENCE_INDEX] = sequence;
    frame[UWB_2A2T_DESTINATION_INDEX] = destination[0];
    frame[UWB_2A2T_DESTINATION_INDEX + 1U] = destination[1];
    frame[UWB_2A2T_SOURCE_INDEX] = source[0];
    frame[UWB_2A2T_SOURCE_INDEX + 1U] = source[1];
    frame[UWB_2A2T_FUNCTION_INDEX] = function;
}

static inline uint8_t uwb_2a2t_header_matches(const uint8_t *frame, const uint8_t *destination,
                                                const uint8_t *source, uint8_t function, uint8_t sequence)
{
    return (uint8_t)((frame[UWB_2A2T_SEQUENCE_INDEX] == sequence) &&
                     (frame[UWB_2A2T_FUNCTION_INDEX] == function) &&
                     (frame[UWB_2A2T_DESTINATION_INDEX] == destination[0]) &&
                     (frame[UWB_2A2T_DESTINATION_INDEX + 1U] == destination[1]) &&
                     (frame[UWB_2A2T_SOURCE_INDEX] == source[0]) &&
                     (frame[UWB_2A2T_SOURCE_INDEX + 1U] == source[1]));
}

static inline void uwb_2a2t_set_final_extension(uint8_t *frame, uint8_t slot_id, uint32_t superframe_id)
{
    frame[UWB_2A2T_FINAL_EXTENSION_INDEX] = UWB_2A2T_PROTOCOL_VERSION;
    frame[UWB_2A2T_FINAL_EXTENSION_INDEX + 1U] = slot_id;
    frame[UWB_2A2T_FINAL_EXTENSION_INDEX + 2U] = (uint8_t)superframe_id;
    frame[UWB_2A2T_FINAL_EXTENSION_INDEX + 3U] = (uint8_t)(superframe_id >> 8U);
    frame[UWB_2A2T_FINAL_EXTENSION_INDEX + 4U] = (uint8_t)(superframe_id >> 16U);
    frame[UWB_2A2T_FINAL_EXTENSION_INDEX + 5U] = (uint8_t)(superframe_id >> 24U);
}

static inline uint8_t uwb_2a2t_final_extension_matches(const uint8_t *frame, uint8_t slot_id)
{
    return (uint8_t)((frame[UWB_2A2T_FINAL_EXTENSION_INDEX] == UWB_2A2T_PROTOCOL_VERSION) &&
                     (frame[UWB_2A2T_FINAL_EXTENSION_INDEX + 1U] == slot_id));
}

#endif /* UWB_2A2T_PROTOCOL_H */
