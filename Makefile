.PHONY: all
all: \
	malo/js/vue-2.6.11.js \
	malo/js/vue-2.6.11.min.js \
	malo/js/vue-router-3.1.6.js \
	malo/js/vue-router-3.1.6.min.js

malo/js/vue-2.6.11.js:
	wget https://unpkg.com/vue@2.6.11/dist/vue.js -O $@

malo/js/vue-2.6.11.min.js:
	wget https://unpkg.com/vue@2.6.11/dist/vue.min.js -O $@

malo/js/vue-router-3.1.6.js:
	wget https://unpkg.com/vue-router@3.1.6/dist/vue-router.js -O $@

malo/js/vue-router-3.1.6.min.js:
	wget https://unpkg.com/vue-router@3.1.6/dist/vue-router.min.js -O $@
