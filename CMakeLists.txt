cmake_minimum_required(VERSION 3.12)

project(swarm_dmas DESCRIPTION "SWARM Distributed Multi-Agent System")

set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/conf/cmake/")
set(LIBRARY_OUTPUT_PATH ${CMAKE_BINARY_DIR}/lib)

include(GNUInstallDirs)
find_package(SimGrid 4.0 REQUIRED)
find_package(FSMod 0.3 REQUIRED)
find_package(WRENCH REQUIRED)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++17")

include_directories(include)

set(HEADER_FILES
  include/agents/JobLifecycleTrackerAgent.h
  include/agents/JobSchedulingAgent.h
  include/agents/WorkloadCentralizedSubmissionAgent.h
  include/agents/WorkloadSubmissionAgent.h
  include/policies/CentralizedSchedulingPolicy.h
  include/policies/PythonBiddingSchedulingPolicy.h
  include/policies/PureLocalSchedulingPolicy.h
  include/policies/RandomBiddingSchedulingPolicy.h
  include/policies/SchedulingPolicy.h
  include/ControlMessages.h
  include/info/HPCSystemDescription.h
  include/info/HPCSystemStatus.h
  include/info/JobDescription.h
  include/info/JobLifecycle.h
  include/utils/PythonRunner.h
  include/utils.h
)

set(SOURCE_FILES
  src/agents/JobLifecycleTrackerAgent.cpp
  src/agents/JobSchedulingAgent.cpp
  src/agents/WorkloadCentralizedSubmissionAgent.cpp
  src/agents/WorkloadSubmissionAgent.cpp
  src/policies/SchedulingPolicy.cpp
  src/swarm_dmas.cpp
  src/utils.cpp
)

add_executable(swarm_dmas ${SOURCE_FILES})

add_custom_target(swarm_dmas-platform-file
  COMMAND /bin/sh -c 
    "if [ '${CMAKE_CURRENT_SOURCE_DIR}' != '${CMAKE_CURRENT_BINARY_DIR}' ]; then \
     mkdir -p platforms; \
     /bin/cp -f ${CMAKE_CURRENT_SOURCE_DIR}/platforms/*.xml ${CMAKE_CURRENT_BINARY_DIR}/platforms/ ; \
     fi ;"
  VERBATIM
)

add_custom_target(swarm_dmas-workloads
  COMMAND /bin/sh -c 
    "if [ '${CMAKE_CURRENT_SOURCE_DIR}' != '${CMAKE_CURRENT_BINARY_DIR}' ]; then \
    mkdir -p workloads; \
    /bin/cp -f ${CMAKE_CURRENT_SOURCE_DIR}/data_generation/data/*.json ${CMAKE_CURRENT_BINARY_DIR}/workloads/ ; \
    fi ;"
  VERBATIM
)

add_custom_target(swarm_dmas-python-scripts
  COMMAND /bin/sh -c 
    "if [ '${CMAKE_CURRENT_SOURCE_DIR}' != '${CMAKE_CURRENT_BINARY_DIR}' ]; then \
    mkdir -p python_scripts; \
    /bin/cp -f ${CMAKE_CURRENT_SOURCE_DIR}/python_scripts/*.py ${CMAKE_CURRENT_BINARY_DIR}/python_scripts/ ; \
    fi ;"
  VERBATIM
)

add_custom_target(swarm_dmas-experiments
  COMMAND /bin/sh -c 
    "if [ '${CMAKE_CURRENT_SOURCE_DIR}' != '${CMAKE_CURRENT_BINARY_DIR}' ]; then \
    mkdir -p experiments; \
    /bin/cp -f ${CMAKE_CURRENT_SOURCE_DIR}/experiments/*.json ${CMAKE_CURRENT_BINARY_DIR}/experiments/ ; \
    fi ;"
  VERBATIM
)

add_dependencies(swarm_dmas swarm_dmas-workloads)
add_dependencies(swarm_dmas swarm_dmas-platform-file)
add_dependencies(swarm_dmas swarm_dmas-python-scripts)
add_dependencies(swarm_dmas swarm_dmas-experiments)

if (ENABLE_BATSCHED)
    target_link_libraries(swarm_dmas
            wrench
            ${SimGrid_LIBRARY}
	    ${FSMOD_LIBRARY}
            ${Boost_LIBRARIES}
            ${ZMQ_LIBRARY}
            )
else()
    target_link_libraries(swarm_dmas
            wrench
            ${SimGrid_LIBRARY}
	    ${FSMOD_LIBRARY}
            ${Boost_LIBRARIES}
            )
endif()
