# Sub-folder for storing confidential information, e.g. influxdb tokens

This folder can be used to store some confidential data, it is suggested to pack the parameters in a json file.

For example, a file influxdb.json could be constructed like this:

	{
	"url": "<your url>",
	"org": "<your org>",
	"tokenRead": "<your token>",
	"tokenWrite": "<your token>",
	"bucketRead": "<your bucket>",
	"bucketWrite": "<your bucket>"
	}