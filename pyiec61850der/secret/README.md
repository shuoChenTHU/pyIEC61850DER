# Sub-folder for storing confidential information, e.g. influxdb tokens

This folder can be used to store some confidential data, it is suggested to pack the parameters in a json file.

For example, a file influxdb.json could be constructed like this:

	{
	"read_url": "<place your configuration here>",
	"write_url": "<place your configuration here>",
	"read_org": "<place your configuration here>",
	"write_org": "<place your configuration here>",
	"read_token": "<place your configuration here>",
	"write_token": "<place your configuration here>",
	"read_bucket": "<place your configuration here>",
	"write_bucket": "<place your configuration here>",
	"measurement_read": "<place your configuration here>",
	"measurement_write": "<place your configuration here>"
	}