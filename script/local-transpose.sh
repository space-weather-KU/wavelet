cat resource/wavelet-result-twoyear.txt | \
    ./dist/build/transpose-wavelet-mapper/transpose-wavelet-mapper | \
    sort | \
    ./dist/build/transpose-wavelet-reducer/transpose-wavelet-reducer | \
    ./dist/build/transpose-wavelet-finalizer/transpose-wavelet-finalizer 
