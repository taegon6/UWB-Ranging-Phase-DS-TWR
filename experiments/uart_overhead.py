"""UART timing endpoint definitions."""

METRICS = {
    "record_encode": ("software encode start", "software encode end"),
    "ring_enqueue": ("TRACE_UART_ENQUEUE_START", "TRACE_UART_ENQUEUE_END"),
    "physical_tx": ("TRACE_UART_TX_START", "TRACE_UART_TX_END"),
    "host_arrival": ("device record timestamp", "host monotonic arrival timestamp"),
}
