.PHONY: all
all: \
	netviel/js/vue-2.6.11.js \
	netviel/js/vue-2.6.11.min.js

netviel/js/vue-2.6.11.js:
	wget https://unpkg.com/vue@2.6.11/dist/vue.js -O $@

netviel/js/vue-2.6.11.min.js:
	wget https://unpkg.com/vue@2.6.11/dist/vue.min.js -O $@
