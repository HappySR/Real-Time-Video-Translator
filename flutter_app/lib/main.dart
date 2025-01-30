import 'package:flutter/material.dart';
import 'video_upload.dart';

void main() {
  runApp(MyApp());
}

class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Video Transcription App',
      theme: ThemeData(
        primarySwatch: Colors.blue,
      ),
      home: VideoUploadPage(),
    );
  }
}
