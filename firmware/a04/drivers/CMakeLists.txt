# SPDX-License-Identifier: Apache-2.0
if(CONFIG_AURA_DMIC_NRFX_PDM)
  target_include_directories(app PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../include)
  target_sources(app PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/aura_dmic_nrfx_pdm.c)
endif()
