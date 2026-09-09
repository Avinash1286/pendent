cmake_minimum_required(VERSION 3.20.0)
list(APPEND DTS_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/drivers)
if(NOT DTC_OVERLAY_FILE)
    # This application is an isolated DK integration probe, never an AURA image.
    set(DTC_OVERLAY_FILE "${CMAKE_CURRENT_SOURCE_DIR}/drivers/probe/nrf52840dk_nrf52840.overlay")
endif()
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(aura_a04_integration_probe)
if(NOT CONFIG_SOC_NRF52840 OR NOT CONFIG_BOARD_NRF52840DK)
    message(FATAL_ERROR "A04 integration probe is restricted to nrf52840dk/nrf52840")
endif()
add_subdirectory(drivers)
include(cmake/opus-profile.cmake)
target_link_libraries(opus PUBLIC zephyr_interface)
target_compile_options(opus PRIVATE -ffunction-sections -fdata-sections -fstack-usage)
target_include_directories(app PRIVATE include)
target_sources(app PRIVATE src/aura_opus.c src/aura_archive.c src/aura_journal.c
    src/aura_w25n01gv.c src/aura_w25n01gv_zephyr.c src/aura_recorder.c
    src/aura_audio_zephyr.c src/aura_release_auth.c src/aura_control.c src/aura_storage.c
    src/aura_transfer.c src/zephyr_probe.c)
target_compile_options(app PRIVATE -fstack-usage)
target_link_libraries(app PRIVATE opus)
