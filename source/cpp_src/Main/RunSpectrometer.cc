#include <iostream>
#include <vector>
#include <memory>
#include <fstream>
#include <sstream>
#include <thread>
#include <unistd.h>

#include "HPX14Digitizer.hh"
#include "HBufferPool.hh"
#include "HSpectrometerCUDA.hh"
#include "HCudaHostBufferAllocator.hh"
#include "HBufferAllocatorSpectrometerDataCUDA.hh"
#include "HSimpleMultiThreadedSpectrumDataWriter.hh"
#include "HPeriodicPowerCalculator.hh"
#include "HServer.hh"

#include "HSpectrometerManager.hh"

using namespace hose;

int main(int /*argc*/, char** /*argv*/)
{
    HSpectrometerManager* specManager = new HSpectrometerManager();

    std::thread daemon( &HSpectrometerManager::Run, specManager);

    sleep(120);

    specManager->Shutdown();

    daemon.join();

    return 0;
}
