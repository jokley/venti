function decodeUplink(input) {
     
  var port = input.fPort;
  var bytes = input.bytes;
  
  var data = {};

  var tmp = (bytes[0]<<8 | bytes[1]);
  var hum = (bytes[2]<<8 | bytes[3]);
  var battery = (bytes[4]<<8 | bytes[5]);
  
  data.temperature = (tmp)/100,
  data.humidity = (hum)/100,
  data.trockenmasse =-0.0028*((hum)/100)*((hum)/100)+0.004*((hum)/100)+(87+(((tmp)/100)*0.2677)),
  data.sdef = ((((hum)/100)*-0.05)-(-5))* Math.exp(0.0625*((tmp)/100)),
  data.battery = battery

  
   return {
      data: data,
    }
  }