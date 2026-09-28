// G97 offline JSON-lines runner. Fresh model state for every request; CPU only.
#include "llama.h"
#include "ggml-backend.h"
#include "json.hpp"
#include <algorithm>
#include <chrono>
#include <ctime>
#include <iostream>
#include <string>
#include <vector>
#include <sys/resource.h>
using json = nlohmann::json;
using clock_type = std::chrono::steady_clock;

int main(int argc, char ** argv) {
    if (argc != 2) return 2;
    auto startup = clock_type::now();
    ggml_backend_load_all();
    auto mp = llama_model_default_params(); mp.n_gpu_layers = 0;
    llama_model * model = llama_model_load_from_file(argv[1], mp);
    if (!model) return 3;
    auto cp = llama_context_default_params();
    cp.n_ctx = 4096; cp.n_batch = 512; cp.n_ubatch = 512;
    cp.n_threads = 1; cp.n_threads_batch = 1;
    llama_context * ctx = llama_init_from_model(model, cp);
    if (!ctx) return 4;
    const llama_vocab * vocab = llama_model_get_vocab(model);
    struct rusage usage; getrusage(RUSAGE_SELF, &usage);
    std::cout << json{{"ready",true},{"load_ms",std::chrono::duration<double,std::milli>(clock_type::now()-startup).count()},
                     {"peak_rss_kib",usage.ru_maxrss}}.dump() << std::endl;
    std::string line;
    while (std::getline(std::cin,line)) {
        auto begin = clock_type::now(); auto cpu = std::clock();
        json result;
        try {
            auto input = json::parse(line);
            std::string prompt = input.at("prompt");
            llama_memory_clear(llama_get_memory(ctx),true);
            int n = -llama_tokenize(vocab,prompt.c_str(),prompt.size(),nullptr,0,false,true);
            result["input_tokens"] = n;
            if (n <= 0 || n > 4088) {
                result["text"]=""; result["error"]="context_limit";
            } else {
                std::vector<llama_token> tokens(n);
                if (llama_tokenize(vocab,prompt.c_str(),prompt.size(),tokens.data(),n,false,true)<0)
                    throw std::runtime_error("tokenization");
                for (int pos=0; pos<n; pos+=512) {
                    auto batch=llama_batch_get_one(tokens.data()+pos,std::min(512,n-pos));
                    if (llama_decode(ctx,batch)) throw std::runtime_error("prefill");
                }
                auto * sampler = llama_sampler_init_greedy();
                std::string output; int generated=0;
                for (int step=0; step<8; ++step) {
                    llama_token token=llama_sampler_sample(sampler,ctx,-1);
                    if (llama_vocab_is_eog(vocab,token)) break;
                    char buffer[512];
                    int length=llama_token_to_piece(vocab,token,buffer,sizeof(buffer),0,true);
                    if (length<0) { llama_sampler_free(sampler); throw std::runtime_error("token_piece"); }
                    output.append(buffer,length); ++generated;
                    if (step<7) {
                        auto batch=llama_batch_get_one(&token,1);
                        if (llama_decode(ctx,batch)) { llama_sampler_free(sampler); throw std::runtime_error("decode"); }
                    }
                }
                llama_sampler_free(sampler);
                result["text"]=output; result["output_tokens"]=generated;
            }
        } catch (const std::exception & error) {
            result["text"]=""; result["error"]=error.what();
        }
        getrusage(RUSAGE_SELF,&usage);
        result["ms"]=std::chrono::duration<double,std::milli>(clock_type::now()-begin).count();
        result["cpu_s"]=double(std::clock()-cpu)/CLOCKS_PER_SEC;
        result["peak_rss_kib"]=usage.ru_maxrss;
        std::cout << result.dump(-1,' ',false,json::error_handler_t::replace) << std::endl;
    }
    llama_free(ctx); llama_model_free(model); llama_backend_free();
}
