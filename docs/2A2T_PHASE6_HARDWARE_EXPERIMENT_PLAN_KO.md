# 2A2T Phase 6 Hardware Experiment Plan

`source_type = SYNTHETIC`  
`hardware_verified = false`

## 사전 조건
A1/A2/T1/T2 역할·serial/J-Link ID, firmware commit, UART baud/format, logic channel mapping, 공급전압, 위치·방향을 기록한다. Antenna-delay calibration은 별도 accuracy 실험으로 둔다.

## Stage A — Conservative smoke test
가장 보수적인 manifest를 수동 적용한다. 4/4 link complete, node identity, timeout/late-TX/RX error를 확인하고 UART 4개를 동시에 원본 저장한다. 가능하면 logic analyzer도 원본으로 보존한다. 실패 시 즉시 rollback한다.

## Stage B — Candidate comparison
후보당 10초, 최소 3회, 같은 위치/PHY로 수행한다. complete superframe, link success, timeout, late TX, retry, UART drop, measured period를 저장한다. Fake measurement를 만들지 않는다.

## Stage C — Robustness
CIR/phase on/off, UART load, LOS, 보드 방향을 바꾸며 반복한다. 각 변경은 독립 run으로 기록한다.

## 비교 및 승인
예측/측정 superframe period·rate·link update rate, timeout/late-TX rate, UART drop, 반복 변동성, model error percent를 비교한다. HIL 결과 전까지 어떤 후보도 hardware verified가 아니다.
