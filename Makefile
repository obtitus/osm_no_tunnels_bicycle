push_test_to_cakebox:
	rsync --progress leaflet-gpx-demo.html demo.gpx map185270616.gpx map185270616.html map27232275.html map27232275.gpx ob.cakebox.net:public_html/leaflet-test/
	rsync --progress -r stylesheets javascripts images ob.cakebox.net:public_html/leaflet-test/
