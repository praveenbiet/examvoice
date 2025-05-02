import React from 'react';
import { AppBar, Toolbar, Typography, Container, Box } from '@mui/material';
import MicIcon from '@mui/icons-material/Mic';

function Layout({ children }) {
  return (
    <Box sx={{ flexGrow: 1 }}>
      <AppBar position="static">
        <Toolbar>
          <MicIcon sx={{ mr: 2 }} />
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Voice-Based Exam System
          </Typography>
        </Toolbar>
      </AppBar>
      <Container maxWidth="md" sx={{ mt: 4 }}>
        {children}
      </Container>
    </Box>
  );
}

export default Layout; 