#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stdio.h>

typedef struct {

  uint32_t res_rx_final_tx;
  uint32_t poll_tx_res_rx;
  uint32_t resp_timeout;

} Init_DelayTimes;


typedef struct {

  uint32_t poll_rx_res_tx;
  uint32_t res_tx_final_rx;
  uint32_t final_timeout;

} Resp_DelayTimes;

int getPreambleLength(int txPreambLength);

int getPacLength(int rxPAC);

void getDelayTime_initiator(dwt_config_t *config, uint32_t* res_rx_final_tx, uint32_t* poll_tx_res_rx, uint32_t* resp_timeout);
void getDelayTime_responder(dwt_config_t *config, uint32_t* poll_rx_res_tx, uint32_t* res_tx_final_Rx, uint32_t* final_timeout);
void saveDistancesToTxt(const double* distances, const char* filename, int size);
Init_DelayTimes ds_twr_getDelayTime_initiator(dwt_config_t *config);
Resp_DelayTimes ds_twr_getDelayTime_responder(dwt_config_t *config);


void timer_init_uss(void);
void timer4_irqhandler(void);
float TIMER4_OFTime(void);
uint32_t TIMER4_Check(uint32_t starttime, float clk_time);
uint64_t TIMER4_Check2(uint32_t starttime, float clk_time);

uint64_t get_10_pkt_time(uint8_t preamble_len);

void collect_CIR(FILE *out, uint8_t accum_data[], uint8_t ACCUM_DATA_LEN);
double calculate_CIR(uint8_t accum_data[], uint8_t ACCUM_DATA_LEN);
double normalize_phase(double phase);

#define WINDOW_SIZE 20

typedef struct {
    int window[WINDOW_SIZE];
    int sorted_window[WINDOW_SIZE];
    int index;
} MedianFilter_N;

typedef struct {
    double window[WINDOW_SIZE];
    double sorted_window[WINDOW_SIZE];
    int index;
} MedianFilter_PHASE;

void init_filter_N(MedianFilter_N *filter);
int process_value_N(MedianFilter_N *filter, int new_value);
void init_filter_PHASE(MedianFilter_PHASE *filter);
double process_value_PHASE(MedianFilter_PHASE *filter, double new_value);


typedef enum {
    DB_N30 = (0x00<<2)+3,
    DB_N29 = (0x01<<2)+1,
    DB_N28 = (0x02<<2)+0,
    DB_N27 = (0x01<<2)+3,
    DB_N26 = (0x02<<2)+1,
    DB_N25 = (0x03<<2)+0,
    DB_N24 = (0x02<<2)+3,
    DB_N23 = (0x03<<2)+1,
    DB_N22 = (0x05<<2)+0,
    DB_N21 = (0x03<<2)+3,
    DB_N20 = (0x07<<2)+0,
    DB_N19 = (0x04<<2)+3,
    DB_N18 = (0x06<<2)+1,
    DB_N17 = (0x05<<2)+3,
    DB_N16 = (0x06<<2)+3,
    DB_N15 = (0x07<<2)+3,
    DB_N14 = (0x08<<2)+3,
    DB_N13 = (0x09<<2)+3,
    DB_N12 = (0x0A<<2)+3,
    DB_N11 = (0x0F<<2)+1,
    DB_N10 = (0x0D<<2)+3,
    DB_N9 = (0x0F<<2)+3,
    DB_N8 = (0x11<<2)+3,
    DB_N7 = (0x14<<2)+3,
    DB_N6 = (0x17<<2)+3,
    DB_N5 = (0x1A<<2)+3,
    DB_N4 = (0x1F<<2)+3,
    DB_N3 = (0x24<<2)+3,
    DB_N2 = (0x2A<<2)+3,
    DB_N1 = (0x34<<2)+3,
    Db_N0 = (0x3F<<2)+3
} db_gain_e;






#ifdef __cplusplus
}
#endif
