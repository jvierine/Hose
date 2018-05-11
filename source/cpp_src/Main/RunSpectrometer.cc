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
