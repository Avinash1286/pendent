cmake_minimum_required(VERSION 3.20.0)
# Reuse the reviewed passive PDM/NAND/control bindings without modifying bench.
list(APPEND DTS_ROOT ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/../bench ${CMAKE_CURRENT_SOURCE_DIR}/../drivers)
set(DTC_OVERLAY_FILE "${CMAKE_CURRENT_SOURCE_DIR}/boards/nrf52840dk_nrf52840.overlay")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(aura_a04_radio_dk)
if(NOT CONFIG_SOC_NRF52840 OR NOT CONFIG_BOARD_NRF52840DK OR NOT CONFIG_BT
   OR NOT CONFIG_BT_SMP_SC_ONLY OR NOT CONFIG_USE_DT_CODE_PARTITION
   OR NOT CONFIG_CSPRNG_ENABLED OR NOT CONFIG_HARDWARE_DEVICE_CS_GENERATOR
   OR NOT CONFIG_ENTROPY_NRF5_RNG OR CONFIG_TEST_RANDOM_GENERATOR OR CONFIG_TEST_CSPRNG_GENERATOR)
    message(FATAL_ERROR "Separate A04 radio application requires nrf52840dk/nrf52840, authenticated LE SC, isolated code partition and production nRF CSPRNG")
endif()
add_subdirectory(../drivers ${CMAKE_CURRENT_BINARY_DIR}/aura-drivers)
include(../cmake/opus-profile.cmake)
target_link_libraries(opus PUBLIC zephyr_interface)
target_compile_options(opus PRIVATE -ffunction-sections -fdata-sections -fstack-usage)
target_include_directories(app PRIVATE include ../include)
target_sources(app PRIVATE src/main.c src/aura_gatt_zephyr.c src/aura_pairing_zephyr.c
    ../src/aura_session_auth.c ../src/aura_transfer.c
    ../src/aura_opus.c ../src/aura_archive.c ../src/aura_journal.c
    ../src/aura_recorder.c ../src/aura_audio_zephyr.c
    ../src/aura_w25n01gv.c ../src/aura_w25n01gv_zephyr.c ../src/aura_control.c
    ../src/aura_release_auth.c ../src/aura_storage.c)
target_compile_options(app PRIVATE -fstack-usage -Wall -Wextra)
set_source_files_properties(src/main.c src/aura_gatt_zephyr.c src/aura_pairing_zephyr.c
    PROPERTIES COMPILE_OPTIONS "-Werror")
target_link_libraries(app PRIVATE opus)
