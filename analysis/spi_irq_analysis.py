"""Named metric definitions for SPI and IRQ capture analysis."""

METRIC_ENDPOINTS = {
    "irq_latency": ("IRQ_PIN:rising", "ISR_ACTIVE:rising"),
    "isr_duration": ("ISR_ACTIVE:rising", "ISR_ACTIVE:falling"),
    "spi_status_duration": ("SPI_STATUS:rising", "SPI_STATUS:falling"),
    "spi_frame_duration": ("SPI_FRAME:rising", "SPI_FRAME:falling"),
    "spi_cir_duration": ("SPI_CIR:rising", "SPI_CIR:falling"),
}
