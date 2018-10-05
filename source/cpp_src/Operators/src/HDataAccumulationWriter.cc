#include "HDataAccumulationWriter.hh"

namespace hose
{


HDataAccumulationWriter::HDataAccumulationWriter():
    HDirectoryWriter()
    {};
    
void HDataAccumulationWriter::ExecuteThreadTask()
{
    HLinearBuffer< HDataAccumulationWriter >* tail = nullptr;
    if( this->fBufferPool->GetConsumerPoolSize( this->GetConsumerID() ) != 0 )
    {
        //grab a buffer to process
        HConsumerBufferPolicyCode buffer_code = this->fBufferHandler.ReserveBuffer(this->fBufferPool, tail, this->GetConsumerID() );

        if(buffer_code == HConsumerBufferPolicyCode::success && tail != nullptr)
        {
            std::lock_guard<std::mutex> lock( tail->fMutex );

            //grab the pointer to the accumulation container
            accum_container = &( (sink->GetData())[0] ); //should have buffer size of 1

            //we rely on acquisitions start time, sample index, and sideband/pol flags to uniquely name/stamp a file
            std::stringstream ss;
            ss << fCurrentOutputDirectory;
            ss << "/";
            ss <<  sdata->acquistion_start_second;
            ss << "_";
            ss <<  sdata->leading_sample_index;
            ss << "_";
            ss <<  accum_container->GetSidebandFlag();
            ss <<  accum_container->GetPolarizationFlag();

            std::string noise_power_filename = ss.str() + ".npow";

            //write out the noise diode data
            struct HNoisePowerFileStruct* power_data = CreateNoisePowerFileStruct();
            if(power_data != NULL)
            {
                memcpy( power_data->fHeader.fVersionFlag, NOISE_POWER_HEADER_VERSION, HVERSION_WIDTH);
                power_data->fHeader.fSidebandFlag[0] = accum_container->GetSidebandFlag() ;
                power_data->fHeader.fPolarizationFlag[0] = accum_container->GetPolarizationFlag();
                power_data->fHeader.fStartTime = sdata->acquistion_start_second;
                power_data->fHeader.fSampleRate = sdata->sample_rate;
                power_data->fHeader.fLeadingSampleIndex = sdata->leading_sample_index;
                power_data->fHeader.fSampleLength = (sdata->n_spectra)*(sdata->spectrum_length);
                power_data->fHeader.fAccumulationLength = accum_container->GetAccumulations()->size();
                power_data->fHeader.fSwitchingFrequency =  accum_container->GetNoiseDiodeSwitchingFrequency();
                power_data->fHeader.fBlankingPeriod = accum_container->GetNoiseDiodeBlankingPeriod();
                strcpy(power_data->fHeader.fExperimentName, fExperimentName.c_str() );
                strcpy(power_data->fHeader.fSourceName, fSourceName.c_str() );
                strcpy(power_data->fHeader.fScanName, fScanName.c_str() );
    
                //now point the accumulation data to the right memory block
                power_data->fAccumulations = static_cast< struct HDataAccumulationStruct* >( &((*(accum_container->GetAccumulations()))[0] ) );

                int ret_val = WriteNoisePowerFile(noise_power_filename.c_str(), power_data);
                if(ret_val != HSUCCESS){std::cout<<"file error!"<<std::endl;}

                InitializeNoisePowerFileStruct(power_data);
                DestroyNoisePowerFileStruct(power_data);
            }
        }

        if(tail != nullptr)
        {
            this->fBufferHandler.ReleaseBufferToProducer(this->fBufferPool, tail);
        }
    }
}

bool 
HDataAccumulationWriter::WorkPresent()
{
    return ( this->fBufferPool->GetConsumerPoolSize( this->GetConsumerID() ) != 0 );
}

void 
HDataAccumulationWriter::Idle() 
{
    usleep(10);
}

}