cmake_minimum_required(VERSION 3.21)
project(ic705_qt LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 REQUIRED COMPONENTS Core Gui Qml Quick QuickControls2 QuickDialogs2 Network)

qt_standard_project_setup()
qt_policy(SET QTP0001 NEW)
qt_policy(SET QTP0004 NEW)

qt_add_executable(ic705_qt
    src/main.cpp
    src/spectrum_item.h
    src/spectrum_item.cpp
    src/spectrum_model.h
    src/spectrum_model.cpp
    src/waterfall_item.h
    src/waterfall_item.cpp
    src/waterfall_model.h
    src/waterfall_model.cpp
    src/civ_client.h
    src/civ_client.cpp
    src/ic705_client.h
    src/ic705_client.cpp
    src/csv_replay.h
    src/csv_replay.cpp
    src/csv_recorder.h
    src/csv_recorder.cpp
    src/csv_manager.h
    src/csv_manager.cpp
)

# Force C++ compilation before QML module
set_target_properties(ic705_qt PROPERTIES AUTOMOC ON)

add_subdirectory(qml)

target_link_libraries(ic705_qt
    PRIVATE
        Qt6::Core
        Qt6::Gui
        Qt6::Qml
        Qt6::Quick
        Qt6::QuickControls2
        Qt6::QuickDialogs2
        Qt6::Network
)
