import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:io';
import 'package:image_picker/image_picker.dart';

class VideoUploadPage extends StatefulWidget {
  @override
  _VideoUploadPageState createState() => _VideoUploadPageState();
}

class _VideoUploadPageState extends State<VideoUploadPage> {
  File? _video;

  Future<void> _pickVideo() async {
    final pickedFile = await ImagePicker().pickVideo(source: ImageSource.gallery);
    
    setState(() {
      _video = File(pickedFile!.path);
    });
  }

  Future<void> _uploadVideo() async {
    if (_video == null) return;

    var request = http.MultipartRequest('POST', Uri.parse('http://<your-backend-url>/process_video'));
    
    request.files.add(await http.MultipartFile.fromPath('video', _video!.path));
    
    var response = await request.send();
    
    if (response.statusCode == 200) {
      print('Video uploaded successfully');
      // Handle success response here (e.g., show subtitles options)
      final responseData = await http.Response.fromStream(response);
      final data = jsonDecode(responseData.body);
      // Process data here...
      
      // Navigate to the video player screen or show results...
      
    } else {
      print('Failed to upload video');
      // Handle error response here 
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Upload Video'),
      ),
      body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              ElevatedButton(onPressed: _pickVideo, child: Text('Pick Video')),
              ElevatedButton(onPressed: _uploadVideo, child: Text('Upload Video')),
            ],
          )),
      );
  }
}
