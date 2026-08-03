#pragma once
#include "config.h"
#include "BMSModule.h"
#if ENABLE_CAN_GATEWAY
#include <due_can.h>
#endif

class BMSModuleManager
{
public:
    BMSModuleManager();
    void balanceCells();
    void setupBoards();
    void findBoards();
    void renumberBoardIDs();
    void clearFaults();
    void sleepBoards();
    void wakeBoards();
    void getAllVoltTemp();
    void readSetpoints();
#if ENABLE_CAN_GATEWAY
    void setBatteryID();
#endif
    float getPackVoltage();
    float getAvgTemperature();
    float getAvgCellVolt();
#if ENABLE_CAN_GATEWAY
    void processCANMsg(CAN_FRAME &frame);
#endif
    void printPackSummary();
    void printPackDetails();
    void printInventory();
    void dumpModuleRegisters();

private:
    float packVolt;                         // All modules added together
    float lowestPackVolt;
    float highestPackVolt;
    float lowestPackTemp;
    float highestPackTemp;
    BMSModule modules[MAX_MODULE_ADDR + 1]; // store data for as many modules as we've configured for.
    int numFoundModules;                    // The number of modules that seem to exist
    bool isFaulted;
    
#if ENABLE_CAN_GATEWAY
    void sendBatterySummary();
    void sendModuleSummary(int module);
    void sendCellDetails(int module, int cell);
#endif
    
};
