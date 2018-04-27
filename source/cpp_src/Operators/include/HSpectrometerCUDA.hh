#ifndef HSpectrometerCUDA_HH__
#define HSpectrometerCUDA_HH__

#include <iostream>
#include <ostream>
#include <ios>
#include <fstream>
#include <sstream>
#include <thread>
#include <map>
#include <utility>
#include <stdint.h>

#include "HLinearBuffer.hh"
#include "HBufferPool.hh"
#include "HConsumerProducer.hh"

#include "spectrometer.h"

#include "HPeriodicPowerCalculator.hh"

namespace hose
{

/*
*File: HSpectrometerCUDA.hh
*Class: HSpectrometerCUDA
*Author: J. Barrett
*Email: barrettj@mit.edu
*Date:
*Description: unsigned short int version
*/

//template< typename XSourceBufferItemType, typename XSinkBufferItemType, typename XConsumerSourceBufferHandlerPolicyType, typename XProducerSinkBufferHandlerPolicyType > 

class HSpectrometerCUDA: public HConsumerProducer< uint16_t, spectrometer_data, HConsumerBufferHandler_Wait< uint16_t >, HProducerBufferHandler_Steal< spectrometer_data > >
{

    public:
        HSpectrometerCUDA(size_t spectrum_length, size_t n_averages);  //spec size and averages are fixed at constuction time
        virtual ~HSpectrometerCUDA();

        //access to the power calculator for config
        HPeriodicPowerCalculator< uint16_t >* GetPowerCalculator() {return &fPowerCalc;};

    private:

        virtual void ExecuteThreadTask() override;
        virtual bool WorkPresent() override;

        size_t fSpectrumLength;
        size_t fNAverages;

        HPeriodicPowerCalculator< uint16_t > fPowerCalc;

};


}

#endif /* end of include guard: HSpectrometerCUDA */
