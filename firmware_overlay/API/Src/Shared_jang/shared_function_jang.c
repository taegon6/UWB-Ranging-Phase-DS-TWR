#include <boards.h>
#include <deca_spi.h>
#include <examples_defines.h>
#include <port.h>
#include <sdk_config.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include <deca_device_api.h>
#include "shared_function_jang.h"


double PULSE_DURATION = 1/(499.2);

#define PI 3.14159265358979323846



int getPreambleLength(int txPreambLength) {
    switch (txPreambLength) {
    case DWT_PLEN_32: return 32;
    case DWT_PLEN_64: return 64;
    case DWT_PLEN_72: return 72;
    case DWT_PLEN_128: return 128;
    case DWT_PLEN_256: return 256;
    case DWT_PLEN_512: return 512;
    case DWT_PLEN_1024: return 1024;
    case DWT_PLEN_1536: return 1536;
    case DWT_PLEN_2048: return 2048;
    case DWT_PLEN_4096: return 4096;
    default: return 256; // ê¸°ë³¸ ï¿
    }
}

int getPacLength(int rxPAC) {
    switch (rxPAC) {
    case DWT_PAC8: return 8;
    case DWT_PAC16: return 16;
    case DWT_PAC32: return 32;
    default: return 4;
    }
}

int getDATA_RATE(int dataRate)
{
  switch(dataRate){
  case DWT_BR_6M8: return 6800;
  default: return 850;
  }
}

void getDelayTime_initiator(dwt_config_t *config, uint32_t* res_rx_final_tx, uint32_t* poll_tx_res_rx, uint32_t* resp_timeout) {
    int preamble_len = getPreambleLength(config->txPreambLength);
    int sts_len = GET_STS_REG_SET_VALUE((uint16_t)(config->stsLength)) * 8;
    int pac_len = getPacLength(config->rxPAC);
    int sfd_len = 8;
    //float Tsymbol = 4 * 128 * 0.002003; // [usec]
    float Tsymbol = 4 * 127 * 0.002003; // [usec]
    int Tbit = ((19 + 17 * 8) / 0.85); // [usec]

    if (config->stsMode != DWT_STS_MODE_OFF) {
        // STS mode ê´€ì¶”ï¿½ ï¿½ì—… ï¿½ìš” ï¿½ê¸°ì¶”ï¿½
        if ((config->pdoaMode == DWT_PDOA_M1) || (config->pdoaMode == DWT_PDOA_M0)) {
            // In PDOA mode 1, number of accumulated symbols is the whole length of the STS
        } else {
            // In PDOA mode 3 number of accumulated symbols is half of the length of STS symbols
        }
    }

    config->sfdTO = (preamble_len + 1 + sfd_len - pac_len); // SFD timeout (preamble length + 1 + SFD length - PAC size). Used in RX only.

    int Tframe = Tsymbol * (preamble_len + sfd_len) + Tbit + 26;
    *res_rx_final_tx = (1000 + 7 + Tframe);
    *poll_tx_res_rx = (1000);
    *resp_timeout = (uint32_t)Tframe + 100;

}

void getDelayTime_responder(dwt_config_t *config, uint32_t* poll_rx_res_tx, uint32_t* res_tx_final_Rx, uint32_t* final_timeout) {
    int preamble_len = getPreambleLength(config->txPreambLength);
    int sts_len = GET_STS_REG_SET_VALUE((uint16_t)(config->stsLength)) * 8;
    int pac_len = getPacLength(config->rxPAC);
    int sfd_len = 8;
    //float Tsymbol = 4 * 128 * 0.002003; // [usec]
    float Tsymbol = 4 * 127 * 0.002003; // [usec]
    int Tbit = ((19 + 17 * 8) / 0.85); // [usec]

    if (config->stsMode != DWT_STS_MODE_OFF) {
        // STS mode ê´€ì¶”ï¿½ ï¿½ì—… ï¿½ìš” ï¿½ê¸°ì¶”ï¿½
        if ((config->pdoaMode == DWT_PDOA_M1) || (config->pdoaMode == DWT_PDOA_M0)) {
            // In PDOA mode 1, number of accumulated symbols is the whole length of the STS
        } else {
            // In PDOA mode 3 number of accumulated symbols is half of the length of STS symbols
        }
    }

    config->sfdTO = (preamble_len + 1 + sfd_len - pac_len); // SFD timeout (preamble length + 1 + SFD length - PAC size). Used in RX only.

    int Tframe = Tsymbol * (preamble_len + sfd_len) + Tbit + 26;
    //int Tframe = Tsymbol * (preamble_len + sfd_len + sts_len) + Tbit;
    *poll_rx_res_tx = (1000 + 5 + Tframe);
    *res_tx_final_Rx = (1000);
    *final_timeout = (uint32_t)Tframe + 100;

}

void getDelayTime_ss_twr_initiator(dwt_config_t *config, uint32_t* poll_tx_res_rx, uint32_t* resp_timeout) {
    int preamble_len = getPreambleLength(config->txPreambLength);
    int sts_len = GET_STS_REG_SET_VALUE((uint16_t)(config->stsLength)) * 8;
    int pac_len = getPacLength(config->rxPAC);
    int sfd_len = 8;
    float Tsymbol = 4 * 127 * 0.002003; // [usec]
    int Tbit = ((19 + 17 * 8) / 0.85); // [usec]

    if (config->stsMode != DWT_STS_MODE_OFF) {
        if ((config->pdoaMode == DWT_PDOA_M1) || (config->pdoaMode == DWT_PDOA_M0)) {
            // In PDOA mode 1, number of accumulated symbols is the whole length of the STS
        } else {
            // In PDOA mode 3 number of accumulated symbols is half of the length of STS symbols
        }
    }

    config->sfdTO = (preamble_len + 1 + sfd_len - pac_len); // SFD timeout (preamble length + 1 + SFD length - PAC size). Used in RX only.

    int Tframe = Tsymbol * (preamble_len + sfd_len) + Tbit + 26;
    *poll_tx_res_rx = (1000);
    *resp_timeout = (uint32_t)Tframe + 100;

}

void getDelayTime_ss_twr_responder(dwt_config_t *config, uint32_t* poll_rx_res_tx) {
    int preamble_len = getPreambleLength(config->txPreambLength);
    int sts_len = GET_STS_REG_SET_VALUE((uint16_t)(config->stsLength)) * 8;
    int pac_len = getPacLength(config->rxPAC);
    int sfd_len = 8;
    float Tsymbol = 4 * 127 * 0.002003; // [usec]
    int Tbit = ((19 + 17 * 8) / 0.85); // [usec]

    if (config->stsMode != DWT_STS_MODE_OFF) {
        if ((config->pdoaMode == DWT_PDOA_M1) || (config->pdoaMode == DWT_PDOA_M0)) {
            // In PDOA mode 1, number of accumulated symbols is the whole length of the STS
        } else {
            // In PDOA mode 3 number of accumulated symbols is half of the length of STS symbols
        }
    }

    config->sfdTO = (preamble_len + 1 + sfd_len - pac_len); // SFD timeout (preamble length + 1 + SFD length - PAC size). Used in RX only.

    int Tframe = Tsymbol * (preamble_len + sfd_len) + Tbit + 26;
    //int Tframe = Tsymbol * (preamble_len + sfd_len + sts_len) + Tbit;
    *poll_rx_res_tx = (1000 + 5 + Tframe);

}

void saveDistancesToTxt(const double* distances, const char* filename, int size) 
{
    FILE* file = fopen(filename, "w");
    if (file == NULL) {
        return;
    }
    for (int i = 0; i < size; ++i) {
        fprintf(file, "%f\n", distances[i]);
    }
    fclose(file);
}

void timer_init_uss(void){
    
    NRF_TIMER4->TASKS_STOP  = 1;
    NRF_TIMER4->TASKS_CLEAR = 1;

    NRF_TIMER4->MODE = TIMER_MODE_MODE_Timer;

    NRF_TIMER4->BITMODE = TIMER_BITMODE_BITMODE_32Bit;

    NRF_TIMER4->PRESCALER = 3;
    
    //NRF_TIMER4->CC[0] = (float)2 * ((float)period_us);

    NRF_TIMER4->INTENSET = 4294967295; //65536
    
    NRF_TIMER4->SHORTS = TIMER_SHORTS_COMPARE0_CLEAR_Msk;

    NVIC_EnableIRQ(TIMER4_IRQn);

    NRF_TIMER4->TASKS_START = 1;

}
//static int testCount= 0;
void TIMER4_IRQHandler(void){
    // overflow time = 2 ^32 * 0.25us(16M/4) = 2^10 * 3 = 2M sec... 
    if(NRF_TIMER4->EVENTS_COMPARE[0] == 1){
        
        NRF_TIMER4->EVENTS_COMPARE[0] = 0;
        NRF_TIMER4->TASKS_STOP  = 1;
        NRF_TIMER4->TASKS_CLEAR = 1;
        printf("IRQon");
        
    }
}

float TIMER4_OFTime(){
    int pre = NRF_TIMER4->PRESCALER;
    float clk_time = 1 / ( (16) / pow(2.0, pre));
    
    //printf("prescaler = %d, clk time = %f us\n", pre, clk_time);
    //printf("timer overflow time = %f second \n",pow(2.0, 32)* clk_time/ 1000000);
    return clk_time;
}
uint32_t TIMER4_Check(uint32_t starttime, float clk_time){
        NRF_TIMER4->TASKS_CAPTURE[1] = 1;
        uint32_t end_time = NRF_TIMER4->CC[1];
        uint32_t ticks = end_time - starttime;
        //printf("clock = %f", clk_time);
        //printf("elapsed_time = %f us, current time = %f us previous time = %f us/", ticks * clk_time, end_time * clk_time, starttime * clk_time);
        printf("\nelapsed_time = %f us\n", ticks * clk_time);
        return end_time;
}

uint64_t TIMER4_Check2(uint32_t starttime, float clk_time){

      NRF_TIMER4->TASKS_CAPTURE[1] = 1;
      uint32_t end_time = NRF_TIMER4->CC[1];
      uint32_t ticks = end_time - starttime;
      uint64_t result = ticks * clk_time;
      return result;
}


uint64_t get_10_pkt_time(uint8_t preamble_len)
{
  switch (preamble_len)
  {
    case DWT_PLEN_64: return 108000 * 11;
    case DWT_PLEN_128: return 108000 * 11;
    case DWT_PLEN_256: return 109000 * 11;
    case DWT_PLEN_512: return 111000 * 11;
    case DWT_PLEN_1024: return 115000 * 11;
    case DWT_PLEN_2048: return 122000 * 11;
    case DWT_PLEN_4096: return 136000 * 11;
    default: return 108000 * 11; 
  }
}




// Only SP0 Mode
Init_DelayTimes ds_twr_getDelayTime_initiator(dwt_config_t *config) 
{
    int preamble_code_index = config->txCode;
    int preamble_length = getPreambleLength(config->txPreambLength);
    int PSDU_DATA_RATE = getDATA_RATE(config->dataRate); // 850, 6800 Áß ÇÏ³ª
    int pac_len = getPacLength(config->rxPAC);
    int sfd_length = 8; // SFD length
    
    config->sfdTO = (preamble_length + 1 + sfd_length - pac_len); // SFD timeout °è»ê

    int payload_byte_values[2] = {15, 24}; // poll: 12byte, response: 15byte, final: 24byte
    int preamble_code_length = 0, delta_length = 0, Number_of_Chips_per_Symbol = 0;
    int total_payload_bit = 0, chips_per_symbol = 0;
    double SHR_Symbol_duration = 0, PHR_Symbol_Duration = 0, PSDU_Symbol_Duration = 0;
    double SHR_DURATION = 0, PHR_PSDU_DURATION = 0;

    // °á°ú¸¦ ÀúÀåÇÒ º¯¼öµé ¼±¾ð
    double poll_duration, response_duration, final_duration;

    // SHR °è»ê
    if (preamble_code_index >= 1 && preamble_code_index <= 8)
    {
        preamble_code_length = 31;
        delta_length = 16;
    } 
    else if (preamble_code_index >= 9 && preamble_code_index <= 24) 
    {
        preamble_code_length = 127;
        delta_length = 4;
    } 

    Number_of_Chips_per_Symbol = preamble_code_length * delta_length;
    SHR_Symbol_duration = Number_of_Chips_per_Symbol * PULSE_DURATION;
    PHR_Symbol_Duration = 512 * PULSE_DURATION;

    int burst_positions_per_Symbol = 8;
    int chips_per_burst;

    if (PSDU_DATA_RATE == 850)
      chips_per_burst = 64;
    else
      chips_per_burst = 8;

    chips_per_symbol = chips_per_burst * burst_positions_per_Symbol;
    PSDU_Symbol_Duration = PULSE_DURATION * chips_per_symbol;

    SHR_DURATION = (preamble_length + sfd_length) * SHR_Symbol_duration;
    

    for (int i = 0; i < 2; i++) 
    {
        int PAYLOAD_BYTE_VALUE = payload_byte_values[i];
        total_payload_bit = PAYLOAD_BYTE_VALUE * 8 + 48 * ceil((double)PAYLOAD_BYTE_VALUE * 8 / 330);

        PHR_PSDU_DURATION = 21 * PHR_Symbol_Duration + total_payload_bit * PSDU_Symbol_Duration;

        // ÆÐÅ¶ °á°ú¸¦ ÀúÀå
        if (i == 0) 
            response_duration = SHR_DURATION + PHR_PSDU_DURATION;
        else 
            final_duration = SHR_DURATION + PHR_PSDU_DURATION; 
    }

    Init_DelayTimes result;

    if (PSDU_DATA_RATE == 6800)
    {
      result.res_rx_final_tx = 700;
      result.poll_tx_res_rx = 719 + (int)final_duration;
      result.resp_timeout = (int)response_duration + 100;
    }
    else
    {
      result.res_rx_final_tx = 700;
      result.poll_tx_res_rx = 700 + (int)final_duration;
      result.resp_timeout = (int)response_duration + 100;
    }

    return result;
}



Resp_DelayTimes ds_twr_getDelayTime_responder(dwt_config_t *config) 
{
    int preamble_code_index = config->txCode;
    int preamble_length = getPreambleLength(config->txPreambLength);
    int PSDU_DATA_RATE = getDATA_RATE(config->dataRate); // 850, 6800 Áß ÇÏ³ª
    int pac_len = getPacLength(config->rxPAC);
    int sfd_length = 8; // SFD length
    
    config->sfdTO = (preamble_length + 1 + sfd_length - pac_len); // SFD timeout °è»ê

    int payload_byte_values[2] = {15, 24}; // poll: 12byte, response: 15byte, final: 24byte
    int preamble_code_length = 0, delta_length = 0, Number_of_Chips_per_Symbol = 0;
    int total_payload_bit = 0, chips_per_symbol = 0;
    double SHR_Symbol_duration = 0, PHR_Symbol_Duration = 0, PSDU_Symbol_Duration = 0;
    double SHR_DURATION = 0, PHR_PSDU_DURATION = 0;

    // °á°ú¸¦ ÀúÀåÇÒ º¯¼öµé ¼±¾ð
    int poll_duration, response_duration, final_duration;

    // SHR °è»ê
    if (preamble_code_index >= 1 && preamble_code_index <= 8)
    {
        preamble_code_length = 31;
        delta_length = 16;
    } 
    else if (preamble_code_index >= 9 && preamble_code_index <= 24) 
    {
        preamble_code_length = 127;
        delta_length = 4;
    } 

    Number_of_Chips_per_Symbol = preamble_code_length * delta_length;
    SHR_Symbol_duration = Number_of_Chips_per_Symbol * PULSE_DURATION;
    PHR_Symbol_Duration = 512 * PULSE_DURATION;

    int burst_positions_per_Symbol = 8;
    int chips_per_burst;

    if (PSDU_DATA_RATE == 850)
      chips_per_burst = 64;
    else
      chips_per_burst = 8;
    chips_per_symbol = chips_per_burst * burst_positions_per_Symbol;
    PSDU_Symbol_Duration = PULSE_DURATION * chips_per_symbol;

    SHR_DURATION = (preamble_length + sfd_length) * SHR_Symbol_duration;

    for (int i = 0; i < 2; i++) 
    {
        int PAYLOAD_BYTE_VALUE = payload_byte_values[i];
        total_payload_bit = PAYLOAD_BYTE_VALUE * 8 + 48 * ceil((double)PAYLOAD_BYTE_VALUE * 8 / 330);

        PHR_PSDU_DURATION = 21 * PHR_Symbol_Duration + total_payload_bit * PSDU_Symbol_Duration;
        // ÆÐÅ¶ °á°ú¸¦ ÀúÀå

        if (i == 0) 
            response_duration = SHR_DURATION + PHR_PSDU_DURATION;
        else 
            final_duration = SHR_DURATION + PHR_PSDU_DURATION; 
    }


    Resp_DelayTimes result;

    if (PSDU_DATA_RATE == 6800)
    {
        result.poll_rx_res_tx = 720 + response_duration;
        result.res_tx_final_rx = 700;
        result.final_timeout = final_duration + 99;
    }
    else
    {
        result.poll_rx_res_tx = 700 + response_duration;
        result.res_tx_final_rx = 750;
        result.final_timeout = final_duration + 99;
    }

    return result;
}

void collect_CIR(FILE *out, uint8_t accum_data[], uint8_t ACCUM_DATA_LEN){

    int32_t real_CIR;
    int32_t img_CIR;
    
    for(int i=1;i<ACCUM_DATA_LEN;i=i+6){
        real_CIR = (int32_t)accum_data[i+2] << 16 | (int32_t)accum_data[i+1] << 8 | (int32_t)accum_data[i];
        img_CIR = (int32_t)accum_data[i+5] << 16 | (int32_t)accum_data[i+4] << 8 | (int32_t)accum_data[i+3];
        if(real_CIR & 0x00800000){
          real_CIR |= 0xff000000;
          //printf("%d,",real_CIR);
          fprintf(out, "%d,",real_CIR);
        }else{
          //printf("%d,",real_CIR);
          fprintf(out, "%d,",real_CIR);
        }
         if(img_CIR & 0x00800000){
          img_CIR |= 0xff000000;
          //printf("%d",img_CIR);
          fprintf(out, "%d,",img_CIR);
        }else{
          //printf("%d",img_CIR);
          fprintf(out, "%d,",img_CIR);
        }
        //printf("|");
        fprintf(out, "|");
    }
}

double calculate_CIR(uint8_t accum_data[], uint8_t ACCUM_DATA_LEN)
{
    int32_t real_CIR = (int32_t)accum_data[ACCUM_DATA_LEN - 6];
    real_CIR |= ((int32_t)accum_data[ACCUM_DATA_LEN - 5] << 8);
    real_CIR |= ((int32_t)(accum_data[ACCUM_DATA_LEN - 4] & 0x03) << 16);

    int32_t img_CIR = (int32_t)accum_data[ACCUM_DATA_LEN - 3];
    img_CIR |= ((int32_t)accum_data[ACCUM_DATA_LEN - 2] << 8);
    img_CIR |= ((int32_t)(accum_data[ACCUM_DATA_LEN - 1] & 0x03) << 16);

    if (real_CIR & 0x020000) {
        real_CIR |= 0xfffc0000;
    }
    if (img_CIR & 0x020000) {
        img_CIR |= 0xfffc0000;
    }

    return round(atan2((double)img_CIR, (double)real_CIR) * 1000.0) / 1000.0;
}

double normalize_phase(double phase)
{
    if (phase < 0) {
        phase += 2 * PI * ceil(-phase / (2 * PI));
    }
    return fmod(phase, 2 * PI);
}

static void insert_and_sort_N(MedianFilter_N *filter, int new_value)
{
    int old_value = filter->window[filter->index];
    filter->window[filter->index] = new_value;
    filter->index = (filter->index + 1) % WINDOW_SIZE;

    int i;
    for (i = 0; i < WINDOW_SIZE; i++) {
        if (filter->sorted_window[i] == old_value) {
            break;
        }
    }
    for (; i < WINDOW_SIZE - 1; i++) {
        filter->sorted_window[i] = filter->sorted_window[i + 1];
    }
    for (i = WINDOW_SIZE - 2; i >= 0 && filter->sorted_window[i] > new_value; i--) {
        filter->sorted_window[i + 1] = filter->sorted_window[i];
    }
    filter->sorted_window[i + 1] = new_value;
}

static void insert_and_sort_PHASE(MedianFilter_PHASE *filter, double new_value)
{
    double old_value = filter->window[filter->index];
    filter->window[filter->index] = new_value;
    filter->index = (filter->index + 1) % WINDOW_SIZE;

    int i;
    for (i = 0; i < WINDOW_SIZE; i++) {
        if (filter->sorted_window[i] == old_value) {
            break;
        }
    }
    for (; i < WINDOW_SIZE - 1; i++) {
        filter->sorted_window[i] = filter->sorted_window[i + 1];
    }
    for (i = WINDOW_SIZE - 2; i >= 0 && filter->sorted_window[i] > new_value; i--) {
        filter->sorted_window[i + 1] = filter->sorted_window[i];
    }
    filter->sorted_window[i + 1] = new_value;
}

void init_filter_N(MedianFilter_N *filter)
{
    for (int i = 0; i < WINDOW_SIZE; i++) {
        filter->window[i] = 0;
        filter->sorted_window[i] = 0;
    }
    filter->index = 0;
}

int process_value_N(MedianFilter_N *filter, int new_value)
{
    insert_and_sort_N(filter, new_value);
    return filter->sorted_window[WINDOW_SIZE / 2];
}

void init_filter_PHASE(MedianFilter_PHASE *filter)
{
    for (int i = 0; i < WINDOW_SIZE; i++) {
        filter->window[i] = 0;
        filter->sorted_window[i] = 0;
    }
    filter->index = 0;
}

double process_value_PHASE(MedianFilter_PHASE *filter, double new_value)
{
    insert_and_sort_PHASE(filter, new_value);
    return filter->sorted_window[WINDOW_SIZE / 2];
}